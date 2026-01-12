from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, Response
from flask_login import login_required, current_user
from ..models import db, ItemLPU, Tecnico, TecnicoStock, StockMovement, Chamado, SolicitacaoReposicao, Notification, ItemLPUPrecoHistorico
from ..services.stock_service import StockService
from ..services.tecnico_service import TecnicoService
from ..decorators import admin_required
from sqlalchemy import func
from datetime import datetime, timedelta
import csv
from io import StringIO

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/controle')
@login_required
@admin_required
def controle_estoque():
    # 1. Carrega itens (Gerais - sem cliente específico ou todos se preferir)
    # Ajuste: Mostra itens gerais (cliente_id=None) para o almoxarifado central
    itens = ItemLPU.query.filter_by(cliente_id=None).order_by(ItemLPU.nome).all()

    # 2. Carrega Técnicos (CORRIGIDO: page=None para retornar lista)
    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)

    # 3. Matriz de Estoque
    stock_data = TecnicoStock.query.all()
    matrix = {}
    for s in stock_data:
        if s.tecnico_id not in matrix:
            matrix[s.tecnico_id] = {}
        matrix[s.tecnico_id][s.item_lpu_id] = s.quantidade

    # 4. Contagem de solicitações pendentes (para badge no menu)
    pendentes_reposicao = SolicitacaoReposicao.query.filter_by(status='Pendente').count()

    return render_template('stock_control.html',
        itens=itens,
        tecnicos=tecnicos,
        matrix=matrix,
        pendentes_reposicao=pendentes_reposicao
    )

@stock_bp.route('/movimentar', methods=['POST'])
@login_required
@admin_required
def movimentar_estoque():
    try:
        tipo = request.form.get('tipo_movimento')
        tecnico_id = request.form.get('tecnico_id')
        item_id = request.form.get('item_id')
        qtd = int(request.form.get('quantidade', 0))
        obs = request.form.get('observacao')

        if not all([tipo, tecnico_id, item_id, qtd]):
            flash('Dados incompletos.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        if tipo == 'ENVIO':
            StockService.transferir_sede_para_tecnico(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'✅ Enviado {qtd}un para o técnico.', 'success')
            
        elif tipo == 'DEVOLUCAO':
            StockService.devolver_tecnico_para_sede(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'✅ Recebido {qtd}un do técnico.', 'info')
            
        elif tipo == 'AJUSTE':
            StockService.ajustar_saldo(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'⚠️ Saldo ajustado para {qtd}un.', 'warning')

    except Exception as e:
        flash(f'Erro na movimentação: {str(e)}', 'danger')

    return redirect(url_for('stock.controle_estoque'))

# --- NOVAS ROTAS DE GESTÃO DE CATÁLOGO ---

@stock_bp.route('/item/adicionar', methods=['POST'])
@login_required
@admin_required
def adicionar_item():
    try:
        nome = request.form.get('nome')
        if not nome:
            flash('Nome do item é obrigatório.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        # Verifica duplicidade
        exists = ItemLPU.query.filter_by(nome=nome, cliente_id=None).first()
        if exists:
            flash(f'O item "{nome}" já existe.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        # Valores financeiros (novos campos)
        valor_custo = float(request.form.get('valor_custo', 0) or 0)
        valor_receita = float(request.form.get('valor_receita', 0) or 0)

        # Cria novo item com custos
        novo_item = ItemLPU(
            nome=nome,
            valor_custo=valor_custo,
            valor_receita=valor_receita,
            cliente_id=None  # Item de estoque geral
        )
        db.session.add(novo_item)
        db.session.commit()
        flash(f'Item "{nome}" adicionado com sucesso!', 'success')

    except Exception as e:
        flash(f'Erro ao adicionar item: {str(e)}', 'danger')

    return redirect(url_for('stock.controle_estoque'))


@stock_bp.route('/item/<int:item_id>/atualizar', methods=['POST'])
@login_required
@admin_required
def atualizar_item(item_id):
    """Atualiza dados de um item (nome, custo, receita) e registra histórico de preços."""
    try:
        item = ItemLPU.query.get_or_404(item_id)

        # Captura valores ANTES da alteração
        custo_anterior = item.valor_custo
        receita_anterior = item.valor_receita

        # Atualizar campos
        if request.form.get('nome'):
            item.nome = request.form.get('nome')

        novo_custo = float(request.form.get('valor_custo', 0) or 0)
        nova_receita = float(request.form.get('valor_receita', 0) or 0)

        # Verifica se houve alteração de preço
        preco_alterado = (custo_anterior != novo_custo) or (receita_anterior != nova_receita)

        if preco_alterado:
            # Registra histórico de alteração
            historico = ItemLPUPrecoHistorico(
                item_lpu_id=item.id,
                valor_custo_anterior=custo_anterior,
                valor_receita_anterior=receita_anterior,
                valor_custo_novo=novo_custo,
                valor_receita_novo=nova_receita,
                motivo=request.form.get('motivo_alteracao', 'Atualização via catálogo'),
                alterado_por_id=current_user.id
            )
            db.session.add(historico)

        # Aplica novos valores
        item.valor_custo = novo_custo
        item.valor_receita = nova_receita

        db.session.commit()

        if preco_alterado:
            flash(f'Item "{item.nome}" atualizado! Alteração de preço registrada no histórico.', 'success')
        else:
            flash(f'Item "{item.nome}" atualizado com sucesso!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar item: {str(e)}', 'danger')

    return redirect(url_for('stock.controle_estoque'))


@stock_bp.route('/api/item/<int:item_id>')
@login_required
def get_item(item_id):
    """API: Retorna dados de um item."""
    item = ItemLPU.query.get_or_404(item_id)
    return jsonify(item.to_dict())


@stock_bp.route('/api/itens')
@login_required
def get_itens():
    """API: Lista todos os itens com custos."""
    itens = ItemLPU.query.filter_by(cliente_id=None).order_by(ItemLPU.nome).all()
    return jsonify([item.to_dict() for item in itens])


@stock_bp.route('/api/item/<int:item_id>/historico-precos')
@login_required
def api_historico_precos(item_id):
    """API: Retorna histórico de alterações de preço de um item."""
    item = ItemLPU.query.get_or_404(item_id)
    historico = ItemLPUPrecoHistorico.query.filter_by(
        item_lpu_id=item_id
    ).order_by(ItemLPUPrecoHistorico.data_alteracao.desc()).limit(50).all()

    return jsonify({
        'item': item.to_dict(),
        'historico': [h.to_dict() for h in historico],
        'total_alteracoes': len(historico)
    })


@stock_bp.route('/api/historico-precos/resumo')
@login_required
@admin_required
def api_resumo_historico_precos():
    """API: Resumo das últimas alterações de preços (todos os itens)."""
    # Últimas 30 alterações
    alteracoes = ItemLPUPrecoHistorico.query.order_by(
        ItemLPUPrecoHistorico.data_alteracao.desc()
    ).limit(30).all()

    # Estatísticas
    total_alteracoes = ItemLPUPrecoHistorico.query.count()
    itens_alterados = db.session.query(
        func.count(func.distinct(ItemLPUPrecoHistorico.item_lpu_id))
    ).scalar() or 0

    # Variação média de custo (últimas 30 dias)
    from datetime import timedelta
    data_limite = datetime.now() - timedelta(days=30)
    alteracoes_recentes = ItemLPUPrecoHistorico.query.filter(
        ItemLPUPrecoHistorico.data_alteracao >= data_limite
    ).all()

    variacoes_custo = []
    for alt in alteracoes_recentes:
        if alt.variacao_custo is not None:
            variacoes_custo.append(alt.variacao_custo)

    variacao_media = sum(variacoes_custo) / len(variacoes_custo) if variacoes_custo else 0

    return jsonify({
        'alteracoes_recentes': [a.to_dict() for a in alteracoes],
        'total_alteracoes': total_alteracoes,
        'itens_com_historico': itens_alterados,
        'variacao_media_custo_30d': round(variacao_media, 2)
    })


@stock_bp.route('/item/<int:item_id>/deletar', methods=['POST'])
@login_required
@admin_required
def deletar_item(item_id):
    try:
        item = ItemLPU.query.get_or_404(item_id)
        
        # Verifica se há estoque em posse de alguém
        em_uso = TecnicoStock.query.filter_by(item_lpu_id=item_id).filter(TecnicoStock.quantidade > 0).first()
        
        if em_uso:
            flash(f'Não é possível excluir "{item.nome}". Há técnicos com saldo positivo deste item.', 'danger')
        else:
            db.session.delete(item)
            db.session.commit()
            flash(f'Item "{item.nome}" removido do catálogo.', 'success')
            
    except Exception as e:
        # Geralmente erro de Foreign Key se houver histórico antigo
        db.session.rollback()
        flash(f'Não foi possível excluir. O item pode ter histórico de movimentações.', 'warning')

    return redirect(url_for('stock.controle_estoque'))


# ==============================================================================
# DASHBOARD DE CUSTOS DE MATERIAIS
# ==============================================================================

@stock_bp.route('/relatorio')
@login_required
@admin_required
def relatorio_materiais():
    """Dashboard com relatório de custos de materiais."""
    # Período padrão: último mês
    data_fim = datetime.now().date()
    data_inicio = data_fim - timedelta(days=30)

    # Filtros da query string
    if request.args.get('data_inicio'):
        data_inicio = datetime.strptime(request.args.get('data_inicio'), '%Y-%m-%d').date()
    if request.args.get('data_fim'):
        data_fim = datetime.strptime(request.args.get('data_fim'), '%Y-%m-%d').date()

    # 1. Total de peças usadas no período (movimentações tipo USO)
    uso_periodo = db.session.query(
        func.count(StockMovement.id).label('total_movs'),
        func.sum(StockMovement.quantidade).label('total_pecas')
    ).filter(
        StockMovement.tipo_movimento == 'USO',
        func.date(StockMovement.data_criacao) >= data_inicio,
        func.date(StockMovement.data_criacao) <= data_fim
    ).first()

    # 2. Custo total de peças em chamados no período
    custo_periodo = db.session.query(
        func.sum(Chamado.custo_peca).label('custo_total')
    ).filter(
        Chamado.data_atendimento >= data_inicio,
        Chamado.data_atendimento <= data_fim,
        Chamado.custo_peca > 0
    ).scalar() or 0

    # 3. Top 5 peças mais usadas
    top_pecas = db.session.query(
        ItemLPU.nome,
        ItemLPU.valor_custo,
        func.sum(StockMovement.quantidade).label('qtd_usada')
    ).join(
        StockMovement, StockMovement.item_lpu_id == ItemLPU.id
    ).filter(
        StockMovement.tipo_movimento == 'USO',
        func.date(StockMovement.data_criacao) >= data_inicio,
        func.date(StockMovement.data_criacao) <= data_fim
    ).group_by(ItemLPU.id).order_by(func.sum(StockMovement.quantidade).desc()).limit(5).all()

    # 4. Estoque atual em rua (por técnico)
    estoque_rua = db.session.query(
        func.sum(TecnicoStock.quantidade).label('total')
    ).filter(TecnicoStock.quantidade > 0).scalar() or 0

    # 5. Valor total do estoque em rua
    valor_estoque_rua = db.session.query(
        func.sum(TecnicoStock.quantidade * ItemLPU.valor_custo).label('valor')
    ).join(ItemLPU, TecnicoStock.item_lpu_id == ItemLPU.id).filter(
        TecnicoStock.quantidade > 0
    ).scalar() or 0

    # 6. Movimentações recentes
    movimentacoes_recentes = StockMovement.query.filter(
        func.date(StockMovement.data_criacao) >= data_inicio
    ).order_by(StockMovement.data_criacao.desc()).limit(20).all()

    # 7. Alertas de estoque baixo (técnicos com saldo <= 1)
    alertas_estoque = TecnicoStock.query.filter(
        TecnicoStock.quantidade <= 1,
        TecnicoStock.quantidade > 0
    ).all()

    return render_template('stock_report.html',
        data_inicio=data_inicio,
        data_fim=data_fim,
        total_movs=uso_periodo.total_movs or 0,
        total_pecas=uso_periodo.total_pecas or 0,
        custo_periodo=float(custo_periodo),
        top_pecas=top_pecas,
        estoque_rua=estoque_rua,
        valor_estoque_rua=float(valor_estoque_rua),
        movimentacoes_recentes=movimentacoes_recentes,
        alertas_estoque=alertas_estoque
    )


# ==============================================================================
# EXPORTAÇÃO DE RELATÓRIOS
# ==============================================================================

@stock_bp.route('/exportar/estoque')
@login_required
@admin_required
def exportar_estoque():
    """Exporta posição atual do estoque em CSV."""
    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header
    writer.writerow([
        'Técnico', 'Cidade', 'Estado', 'Peça', 'Quantidade',
        'Custo Unitário', 'Valor Total', 'Última Atualização'
    ])

    # Data
    estoques = TecnicoStock.query.filter(
        TecnicoStock.quantidade > 0
    ).order_by(TecnicoStock.tecnico_id).all()

    for est in estoques:
        custo = float(est.item_lpu.valor_custo or 0) if est.item_lpu else 0
        writer.writerow([
            est.tecnico.nome if est.tecnico else 'N/A',
            est.tecnico.cidade if est.tecnico else '',
            est.tecnico.estado if est.tecnico else '',
            est.item_lpu.nome if est.item_lpu else 'N/A',
            est.quantidade,
            f'{custo:.2f}',
            f'{custo * est.quantidade:.2f}',
            est.data_atualizacao.strftime('%d/%m/%Y %H:%M') if est.data_atualizacao else ''
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=estoque_{datetime.now().strftime("%Y%m%d")}.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


@stock_bp.route('/exportar/movimentacoes')
@login_required
@admin_required
def exportar_movimentacoes():
    """Exporta histórico de movimentações em CSV."""
    # Período
    data_fim = datetime.now().date()
    data_inicio = data_fim - timedelta(days=30)

    if request.args.get('data_inicio'):
        data_inicio = datetime.strptime(request.args.get('data_inicio'), '%Y-%m-%d').date()
    if request.args.get('data_fim'):
        data_fim = datetime.strptime(request.args.get('data_fim'), '%Y-%m-%d').date()

    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header
    writer.writerow([
        'Data', 'Tipo', 'Peça', 'Quantidade', 'Custo Unitário',
        'Técnico Origem', 'Técnico Destino', 'Chamado', 'Observação'
    ])

    # Data
    movs = StockMovement.query.filter(
        func.date(StockMovement.data_criacao) >= data_inicio,
        func.date(StockMovement.data_criacao) <= data_fim
    ).order_by(StockMovement.data_criacao.desc()).all()

    for mov in movs:
        custo = float(mov.item_lpu.valor_custo or 0) if mov.item_lpu else 0
        writer.writerow([
            mov.data_criacao.strftime('%d/%m/%Y %H:%M') if mov.data_criacao else '',
            mov.tipo_movimento,
            mov.item_lpu.nome if mov.item_lpu else 'N/A',
            mov.quantidade,
            f'{custo:.2f}',
            mov.origem_tecnico.nome if mov.origem_tecnico else 'Almoxarifado',
            mov.destino_tecnico.nome if mov.destino_tecnico else 'Almoxarifado',
            mov.chamado_id or '',
            mov.observacao or ''
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=movimentacoes_{data_inicio.strftime("%Y%m%d")}_{data_fim.strftime("%Y%m%d")}.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


@stock_bp.route('/exportar/custos-chamados')
@login_required
@admin_required
def exportar_custos_chamados():
    """Exporta custos de peças por chamado em CSV."""
    # Período
    data_fim = datetime.now().date()
    data_inicio = data_fim - timedelta(days=30)

    if request.args.get('data_inicio'):
        data_inicio = datetime.strptime(request.args.get('data_inicio'), '%Y-%m-%d').date()
    if request.args.get('data_fim'):
        data_fim = datetime.strptime(request.args.get('data_fim'), '%Y-%m-%d').date()

    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header
    writer.writerow([
        'Data', 'Código Chamado', 'Técnico', 'Cidade',
        'Peça Usada', 'Fornecedor', 'Custo Peça',
        'Custo Serviço', 'Custo Total'
    ])

    # Data - chamados com peça
    chamados = Chamado.query.filter(
        Chamado.data_atendimento >= data_inicio,
        Chamado.data_atendimento <= data_fim,
        Chamado.peca_usada.isnot(None),
        Chamado.peca_usada != ''
    ).order_by(Chamado.data_atendimento.desc()).all()

    for c in chamados:
        custo_peca = float(c.custo_peca or 0)
        custo_servico = float(c.custo_atribuido or 0)
        writer.writerow([
            c.data_atendimento.strftime('%d/%m/%Y') if c.data_atendimento else '',
            c.codigo_chamado or f'ID-{c.id}',
            c.tecnico.nome if c.tecnico else 'N/A',
            c.cidade or '',
            c.peca_usada,
            c.fornecedor_peca or 'Empresa',
            f'{custo_peca:.2f}',
            f'{custo_servico:.2f}',
            f'{custo_peca + custo_servico:.2f}'
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=custos_pecas_{data_inicio.strftime("%Y%m%d")}_{data_fim.strftime("%Y%m%d")}.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


# ==============================================================================
# SISTEMA DE SOLICITAÇÃO DE REPOSIÇÃO
# ==============================================================================

@stock_bp.route('/solicitacoes')
@login_required
@admin_required
def listar_solicitacoes():
    """Lista todas as solicitações de reposição."""
    status_filtro = request.args.get('status', 'Pendente')

    query = SolicitacaoReposicao.query

    if status_filtro and status_filtro != 'Todas':
        query = query.filter(SolicitacaoReposicao.status == status_filtro)

    solicitacoes = query.order_by(SolicitacaoReposicao.data_criacao.desc()).all()

    # Contadores
    pendentes = SolicitacaoReposicao.query.filter_by(status='Pendente').count()
    aprovadas = SolicitacaoReposicao.query.filter_by(status='Aprovada').count()

    return render_template('stock_solicitacoes.html',
        solicitacoes=solicitacoes,
        status_filtro=status_filtro,
        pendentes=pendentes,
        aprovadas=aprovadas
    )


@stock_bp.route('/solicitacao/nova', methods=['POST'])
@login_required
def criar_solicitacao():
    """Cria nova solicitação de reposição."""
    try:
        tecnico_id = request.form.get('tecnico_id')
        item_id = request.form.get('item_id')
        quantidade = int(request.form.get('quantidade', 1))
        justificativa = request.form.get('justificativa', '')

        if not all([tecnico_id, item_id]):
            flash('Dados incompletos.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        solicitacao = SolicitacaoReposicao(
            tecnico_id=int(tecnico_id),
            item_lpu_id=int(item_id),
            quantidade=quantidade,
            justificativa=justificativa,
            created_by_id=current_user.id,
            status='Pendente'
        )
        db.session.add(solicitacao)
        db.session.commit()

        flash('Solicitação de reposição criada com sucesso!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar solicitação: {str(e)}', 'danger')

    return redirect(url_for('stock.listar_solicitacoes'))


@stock_bp.route('/solicitacao/<int:id>/aprovar', methods=['POST'])
@login_required
@admin_required
def aprovar_solicitacao(id):
    """Aprova e executa o envio automaticamente."""
    try:
        solicitacao = SolicitacaoReposicao.query.get_or_404(id)

        if solicitacao.status != 'Pendente':
            flash('Esta solicitação já foi processada.', 'warning')
            return redirect(url_for('stock.listar_solicitacoes'))

        # Executa o envio
        StockService.transferir_sede_para_tecnico(
            tecnico_id=solicitacao.tecnico_id,
            item_id=solicitacao.item_lpu_id,
            qtd=solicitacao.quantidade,
            user_id=current_user.id,
            obs=f"Reposição automática - Solicitação #{solicitacao.id}"
        )

        # Atualiza status
        solicitacao.status = 'Enviada'
        solicitacao.aprovado_por_id = current_user.id
        solicitacao.data_resposta = datetime.now()
        solicitacao.resposta_admin = request.form.get('resposta', 'Aprovado e enviado.')

        # Notifica solicitante
        if solicitacao.created_by_id:
            notif = Notification(
                user_id=solicitacao.created_by_id,
                title=f"Reposição Aprovada",
                message=f"Sua solicitação de {solicitacao.quantidade}x {solicitacao.item_lpu.nome} "
                        f"para {solicitacao.tecnico.nome} foi aprovada e enviada.",
                notification_type='success'
            )
            db.session.add(notif)

        db.session.commit()
        flash(f'Solicitação aprovada! {solicitacao.quantidade}x {solicitacao.item_lpu.nome} enviado(s).', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {str(e)}', 'danger')

    return redirect(url_for('stock.listar_solicitacoes'))


@stock_bp.route('/solicitacao/<int:id>/recusar', methods=['POST'])
@login_required
@admin_required
def recusar_solicitacao(id):
    """Recusa uma solicitação."""
    try:
        solicitacao = SolicitacaoReposicao.query.get_or_404(id)

        if solicitacao.status != 'Pendente':
            flash('Esta solicitação já foi processada.', 'warning')
            return redirect(url_for('stock.listar_solicitacoes'))

        motivo = request.form.get('motivo', 'Solicitação recusada.')

        solicitacao.status = 'Recusada'
        solicitacao.aprovado_por_id = current_user.id
        solicitacao.data_resposta = datetime.now()
        solicitacao.resposta_admin = motivo

        # Notifica solicitante
        if solicitacao.created_by_id:
            notif = Notification(
                user_id=solicitacao.created_by_id,
                title=f"Reposição Recusada",
                message=f"Sua solicitação de {solicitacao.quantidade}x {solicitacao.item_lpu.nome} "
                        f"foi recusada.\n\nMotivo: {motivo}",
                notification_type='danger'
            )
            db.session.add(notif)

        db.session.commit()
        flash('Solicitação recusada.', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {str(e)}', 'danger')

    return redirect(url_for('stock.listar_solicitacoes'))


@stock_bp.route('/api/solicitacoes/pendentes')
@login_required
def api_solicitacoes_pendentes():
    """API: Retorna contagem de solicitações pendentes."""
    count = SolicitacaoReposicao.query.filter_by(status='Pendente').count()
    return jsonify({'pendentes': count})


# ==============================================================================
# API DE RESUMO PARA DASHBOARD PRINCIPAL
# ==============================================================================

@stock_bp.route('/api/dashboard/resumo')
@login_required
def api_dashboard_resumo():
    """
    API: Resumo consolidado de métricas de estoque para o dashboard principal.

    Retorna:
    - Estoque em campo (total e valor)
    - Peças usadas no mês
    - Custo de materiais no mês
    - Alertas de estoque baixo
    - Solicitações pendentes
    - Variação de custos
    """
    from datetime import timedelta

    hoje = datetime.now().date()
    inicio_mes = hoje.replace(day=1)

    # 1. Estoque total em campo
    estoque_stats = db.session.query(
        func.count(TecnicoStock.id).label('registros'),
        func.sum(TecnicoStock.quantidade).label('total_pecas'),
        func.sum(TecnicoStock.quantidade * ItemLPU.valor_custo).label('valor_total')
    ).join(ItemLPU, TecnicoStock.item_lpu_id == ItemLPU.id).filter(
        TecnicoStock.quantidade > 0
    ).first()

    # 2. Uso de peças no mês atual
    uso_mes = db.session.query(
        func.count(StockMovement.id).label('movimentacoes'),
        func.sum(StockMovement.quantidade).label('pecas_usadas')
    ).filter(
        StockMovement.tipo_movimento == 'USO',
        func.date(StockMovement.data_criacao) >= inicio_mes
    ).first()

    # 3. Custo de materiais em chamados no mês
    custo_mes = db.session.query(
        func.sum(Chamado.custo_peca).label('total')
    ).filter(
        Chamado.data_atendimento >= inicio_mes,
        Chamado.custo_peca > 0
    ).scalar() or 0

    # 4. Alertas de estoque baixo (quantidade <= 1)
    alertas_baixo = TecnicoStock.query.filter(
        TecnicoStock.quantidade <= 1,
        TecnicoStock.quantidade > 0
    ).count()

    # 5. Solicitações pendentes
    solicitacoes_pendentes = SolicitacaoReposicao.query.filter_by(status='Pendente').count()

    # 6. Variação de custo (últimos 30 dias)
    data_30d = hoje - timedelta(days=30)
    alteracoes_preco = ItemLPUPrecoHistorico.query.filter(
        func.date(ItemLPUPrecoHistorico.data_alteracao) >= data_30d
    ).count()

    # 7. Top 3 peças mais usadas no mês
    top_pecas_mes = db.session.query(
        ItemLPU.nome,
        func.sum(StockMovement.quantidade).label('qtd')
    ).join(
        StockMovement, StockMovement.item_lpu_id == ItemLPU.id
    ).filter(
        StockMovement.tipo_movimento == 'USO',
        func.date(StockMovement.data_criacao) >= inicio_mes
    ).group_by(ItemLPU.id).order_by(
        func.sum(StockMovement.quantidade).desc()
    ).limit(3).all()

    # 8. Técnicos com mais peças em mãos
    tecnicos_mais_estoque = db.session.query(
        Tecnico.nome,
        func.sum(TecnicoStock.quantidade).label('total')
    ).join(
        TecnicoStock, TecnicoStock.tecnico_id == Tecnico.id
    ).filter(
        TecnicoStock.quantidade > 0
    ).group_by(Tecnico.id).order_by(
        func.sum(TecnicoStock.quantidade).desc()
    ).limit(3).all()

    return jsonify({
        'estoque': {
            'total_pecas': estoque_stats.total_pecas or 0,
            'valor_total': float(estoque_stats.valor_total or 0),
            'tecnicos_com_estoque': estoque_stats.registros or 0
        },
        'uso_mes': {
            'movimentacoes': uso_mes.movimentacoes or 0,
            'pecas_usadas': uso_mes.pecas_usadas or 0,
            'custo_materiais': float(custo_mes)
        },
        'alertas': {
            'estoque_baixo': alertas_baixo,
            'solicitacoes_pendentes': solicitacoes_pendentes,
            'alteracoes_preco_30d': alteracoes_preco
        },
        'top_pecas_mes': [
            {'nome': p.nome, 'quantidade': p.qtd} for p in top_pecas_mes
        ],
        'tecnicos_mais_estoque': [
            {'nome': t.nome, 'quantidade': t.total} for t in tecnicos_mais_estoque
        ],
        'periodo': {
            'inicio_mes': inicio_mes.isoformat(),
            'hoje': hoje.isoformat()
        }
    })


@stock_bp.route('/api/dashboard/kpis')
@login_required
def api_dashboard_kpis():
    """
    API: KPIs simplificados para cards do dashboard.
    Retorna apenas os 4 indicadores principais.
    """
    from datetime import timedelta

    hoje = datetime.now().date()
    inicio_mes = hoje.replace(day=1)

    # KPI 1: Peças em campo
    pecas_campo = db.session.query(
        func.sum(TecnicoStock.quantidade)
    ).filter(TecnicoStock.quantidade > 0).scalar() or 0

    # KPI 2: Valor imobilizado
    valor_imobilizado = db.session.query(
        func.sum(TecnicoStock.quantidade * ItemLPU.valor_custo)
    ).join(ItemLPU, TecnicoStock.item_lpu_id == ItemLPU.id).filter(
        TecnicoStock.quantidade > 0
    ).scalar() or 0

    # KPI 3: Custo do mês
    custo_mes = db.session.query(
        func.sum(Chamado.custo_peca)
    ).filter(
        Chamado.data_atendimento >= inicio_mes,
        Chamado.custo_peca > 0
    ).scalar() or 0

    # KPI 4: Alertas pendentes
    alertas = SolicitacaoReposicao.query.filter_by(status='Pendente').count()
    alertas += TecnicoStock.query.filter(
        TecnicoStock.quantidade <= 1,
        TecnicoStock.quantidade > 0
    ).count()

    return jsonify({
        'pecas_em_campo': pecas_campo,
        'valor_imobilizado': float(valor_imobilizado),
        'custo_mes': float(custo_mes),
        'alertas_pendentes': alertas
    })
