from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify
from flask_login import login_required, current_user
import csv
import io
from sqlalchemy import func
# CORREÇÃO AQUI: Importamos Chamado, Pagamento e Tecnico explicitamente
from ..models import ESTADOS_BRASIL, FORMAS_PAGAMENTO, Chamado, Pagamento, Tecnico, Tag, Cliente, db
from ..services.tecnico_service import TecnicoService
from ..services.chamado_service import ChamadoService
from ..services.financeiro_service import FinanceiroService
from ..services.tag_service import TagService
from ..services.saved_view_service import SavedViewService
from ..services.import_service import ImportService
from ..decorators import admin_required

operacional_bp = Blueprint('operacional', __name__)

@operacional_bp.route('/tecnicos/importar', methods=['GET', 'POST'])
@login_required
def importar_tecnicos():
    if request.method == 'POST':
        if 'arquivo_excel' not in request.files:
            flash('Nenhum arquivo enviado.', 'danger')
            return redirect(request.url)
            
        file = request.files['arquivo_excel']
        if file.filename == '':
            flash('Nenhum arquivo selecionado.', 'danger')
            return redirect(request.url)

        if file:
            result = ImportService.importar_tecnicos(file)
            if result['success']:
                flash(result['message'], 'success')
                return redirect(url_for('operacional.tecnicos'))
            else:
                flash(result['message'], 'danger')
                
    return render_template('importar_tecnicos.html')

STATUS_TECNICO = ['Ativo', 'Inativo']
# TIPOS_SERVICO removed: Fetch dynamically from CatalogoServico
STATUS_CHAMADO = ['Pendente', 'Em Andamento', 'Concluído', 'SPARE', 'Cancelado']

# Helper to get Types
def get_tipos_servico():
    from ..models import CatalogoServico
    # Get distinct names or all active
    # Using distinct names used in system + catalog
    return [s.nome for s in CatalogoServico.query.with_entities(CatalogoServico.nome).distinct().order_by(CatalogoServico.nome).all()]


@operacional_bp.route('/')
@login_required
def dashboard():
    tecnico_stats = TecnicoService.get_stats()
    chamado_stats = ChamadoService.get_dashboard_stats()
    financeiro_stats = FinanceiroService.get_pendentes_stats()
    projecao_stats = FinanceiroService.calcular_projecao_mensal()
    lucro_stats = FinanceiroService.get_lucro_real_mensal()
    
    return render_template('dashboard.html',
        total_tecnicos_ativos=tecnico_stats['ativos'],
        chamados_mes=chamado_stats['chamados_mes'],
        valor_total_pendente=tecnico_stats['total_pendente'],
        pagamentos_pendentes=financeiro_stats,
        chamados_por_status=chamado_stats['chamados_por_status'],
        ultimos_chamados=chamado_stats['ultimos'],
        projecao_financeira=projecao_stats,
        lucro_stats=lucro_stats
    )

@operacional_bp.route('/tecnicos')
@login_required
def tecnicos():
    page = request.args.get('page', 1, type=int) # Captura a página
    filters = {
        'estado': request.args.get('estado', ''),
        'cidade': request.args.get('cidade', ''),
        'status': request.args.get('status', ''),
        'pagamento': request.args.get('pagamento', ''),
        'search': request.args.get('search', ''),
        'tag': request.args.get('tag', '') # New filter
    }
    
    # Chama o serviço passando a página
    pagination = TecnicoService.get_all(filters, page=page, per_page=20)
    tecnicos_list = pagination.items # Extrai a lista da página atual
    
    # Get states for dropdown
    # Nota: Idealmente isso viria de cache ou query distinct, mas ok para agora
    all_states = [t.estado for t in tecnicos_list if t.estado] 
    estados_usados = sorted(list(set(all_states)))
    
    # Saved Views
    saved_views = SavedViewService.get_for_user(current_user.id, 'tecnicos')
    
    # Available Tags (for filter dropdown if needed, though usually typing is easier or a separate endpoint)
    # For now, we can get unique tags to show in filter dropdown if desired.
    available_tags = TagService.get_all_unique()

    # Capilaridade Stats
    tecnicos_por_estado = db.session.query(
        Tecnico.estado, func.count(Tecnico.id)
    ).filter(
        Tecnico.status == 'Ativo',
        Tecnico.estado != ''
    ).group_by(Tecnico.estado).all()
    
    # Convert to dict for easier access if needed, or list of tuples is fine
    # Let's clean up state names if null
    tecnicos_por_estado = [(e if e else 'Indefinido', c) for e, c in tecnicos_por_estado]
    
    # Sort by count desc
    tecnicos_por_estado.sort(key=lambda x: x[1], reverse=True)

    return render_template('tecnicos.html',
        tecnicos=tecnicos_list,
        pagination=pagination,  # Passamos o objeto de paginação
        estados=ESTADOS_BRASIL,
        estados_usados=estados_usados,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        estado_filter=filters['estado'],
        cidade_filter=filters['cidade'],
        status_filter=filters['status'],
        pagamento_filter=filters['pagamento'],
        search_filter=filters['search'],
        tag_filter=filters['tag'],
        saved_views=saved_views,
        available_tags=available_tags,
        tecnicos_por_estado=tecnicos_por_estado
    )

# Task 3: Relatórios (Exportação CSV)
@operacional_bp.route('/tecnicos/exportar')
@login_required
def exportar_tecnicos():
    tecnicos = TecnicoService.get_all(page=None)
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Header
    writer.writerow(['ID', 'Nome', 'Cidade', 'Estado', 'Status', 'Valor/Atendimento', 'Banco', 'Chave', 'Total a Pagar', 'Tags'])
    
    # Rows
    for t in tecnicos:
        tags_str = ", ".join([tag.nome for tag in t.tags])
        writer.writerow([
            t.id_tecnico,
            t.nome,
            t.cidade,
            t.estado,
            t.status,
            f"R$ {t.valor_por_atendimento:.2f}".replace('.', ','),
            t.forma_pagamento or '-',
            t.chave_pagamento or '-',
            f"R$ {t.total_a_pagar:.2f}".replace('.', ','),
            tags_str
        ])
    
    return Response(
        output.getvalue().encode('utf-8-sig'), # utf-8-sig for Excel compatibility
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=tecnicos_export.csv"}
    )

@operacional_bp.route('/tecnicos/novo', methods=['GET', 'POST'])
@login_required
def novo_tecnico():
    if request.method == 'POST':
        try:
            TecnicoService.create(request.form)
            # Task 4: Feedback de Usuário
            flash('Técnico cadastrado com sucesso!', 'success')
            return redirect(url_for('operacional.tecnicos'))
        except Exception as e:
            flash(f'Erro ao cadastrar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'})
    
    return render_template('tecnico_form.html',
        tecnico=None,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )

@operacional_bp.route('/tecnicos/<int:id>')
@login_required
def tecnico_detalhes(id):
    tecnico = TecnicoService.get_by_id(id)
    
    # CORREÇÃO AQUI: Uso direto da classe Chamado importada
    chamados = tecnico.chamados.order_by(Chamado.data_atendimento.desc()).all()
    pagamentos = tecnico.pagamentos.all()
    sub_tecnicos = tecnico.sub_tecnicos
    
    return render_template('tecnico_detalhes.html',
        tecnico=tecnico,
        chamados=chamados,
        pagamentos=pagamentos,
        sub_tecnicos=sub_tecnicos
    )

@operacional_bp.route('/tecnicos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_tecnico(id):
    tecnico = TecnicoService.get_by_id(id)
    
    if request.method == 'POST':
        try:
            TecnicoService.update(id, request.form)
            flash('Dados do técnico atualizados com sucesso!', 'success')
            return redirect(url_for('operacional.tecnico_detalhes', id=id))
        except Exception as e:
            flash(f'Erro ao atualizar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'})
    tecnicos_principais = [t for t in tecnicos_principais if t.id != id]
    
    return render_template('tecnico_form.html',
        tecnico=tecnico,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )

@operacional_bp.route('/chamados')
@login_required
def chamados():
    page = request.args.get('page', 1, type=int)
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', ''),
        'tipo': request.args.get('tipo', ''),
        'pago': request.args.get('pago', ''),
        'search': request.args.get('search', '')
    }
    
    pagination = ChamadoService.get_all(filters, page=page, per_page=50) # 50 por página
    chamados_list = pagination.items
    
    # Para o filtro de técnicos no select (apenas ativos para não pesar)
    tecnicos_list = TecnicoService.get_all({'status': 'Ativo'}, page=1, per_page=1000).items
    
    # Task 2: Saved Views
    saved_views = SavedViewService.get_for_user(current_user.id, 'chamados')
    
    return render_template('chamados.html',
        chamados=chamados_list,
        pagination=pagination, # Passamos o objeto de paginação
        tecnicos=tecnicos_list,
        tipos_servico=get_tipos_servico(),
        status_options=STATUS_CHAMADO,
        tecnico_filter=filters['tecnico_id'],
        status_filter=filters['status'],
        tipo_filter=filters['tipo'],
        pago_filter=filters['pago'],
        search_filter=filters['search'],
        saved_views=saved_views
    )

@operacional_bp.route('/api/views/save', methods=['POST'])
@login_required
def salvar_view():
    try:
        data = request.get_json()
        SavedViewService.save_view(current_user.id, data.get('page_route'), data.get('name'), data.get('query_string'))
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 400

@operacional_bp.route('/api/views/<int:id>/delete', methods=['POST'])
@login_required
def deletar_view(id):
    try:
        SavedViewService.delete_view(id, current_user.id)
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 400

@operacional_bp.route('/chamados/criar/multiplo', methods=['POST'])
@login_required
def criar_chamado_multiplo_api():
    """API endpoint for Master-Detail form (batch creation)"""
    try:
        data = request.get_json()
        logistica = data.get('logistica')
        fsas = data.get('fsas')
        
        if not logistica or not fsas:
            return jsonify({'error': 'Dados incompletos'}), 400
            
        ChamadoService.create_multiplo(logistica, fsas)
        
        return jsonify({'message': 'Atendimento registrado com sucesso!'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@operacional_bp.route('/chamados/criar', methods=['GET'])
@login_required
def criar_chamado():
    """Renders the new Master-Detail form for creating chamados"""
    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
    return render_template('chamado_form.html', tecnicos=tecnicos)

@operacional_bp.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    if request.method == 'POST':
        try:
            ChamadoService.create(request.form)
            flash('Chamado registrado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            flash(f'Erro: {str(e)}', 'warning')
            
            # Repopulate form data for template
            tecnicos = TecnicoService.get_all({'status': 'Ativo'})
            return render_template('chamado_form.html',
                chamado=request.form, # Pass dictionary/ImmutableMultiDict directly
                tecnicos=tecnicos,
                tipos_servico=get_tipos_servico(),
                status_options=STATUS_CHAMADO
            )
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=None,
        tecnicos=tecnicos,
        tipos_servico=get_tipos_servico(),
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    chamado = ChamadoService.get_by_id(id)
    
    if request.method == 'POST':
        try:
            ChamadoService.update(id, request.form)
            flash('Chamado atualizado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            flash(f'Erro ao atualizar chamado: {str(e)}', 'danger')
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=chamado,
        tecnicos=tecnicos,
        tipos_servico=get_tipos_servico(),
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status_chamado(id):
    try:
        ChamadoService.update_status(id, request.form.get('status'))
        flash('Status do chamado atualizado.', 'info')
    except Exception as e:

            flash(f'Erro ao atualizar status: {str(e)}', 'danger')
    return redirect(url_for('operacional.chamados'))

@operacional_bp.route('/tecnicos/<int:id>/resumo')
@login_required
def tecnico_resumo(id):
    tecnico = TecnicoService.get_by_id(id)
    return render_template('tecnico_resumo.html', tecnico=tecnico)

@operacional_bp.route('/tecnicos/<int:id>/tags/criar', methods=['POST'])
@login_required
def criar_tag(id):
    try:
        nome = request.form.get('nome')
        cor = request.form.get('cor', '#3B82F6')
        
        if nome:
            TagService.create_tag(id, nome, cor)
            flash('Tag adicionada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar tag: {str(e)}', 'danger')
        
    return redirect(url_for('operacional.tecnico_detalhes', id=id))

@operacional_bp.route('/tags/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_tag(id):
    try:
        tecnico_id = TagService.delete_tag(id)
        flash('Tag removida com sucesso!', 'success')
        return redirect(url_for('operacional.tecnico_detalhes', id=tecnico_id))
    except Exception as e:
        flash(f'Erro ao remover tag: {str(e)}', 'danger')
        return redirect(url_for('operacional.tecnicos'))

@operacional_bp.route('/chamados/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def deletar_chamado(id):
    try:
        from ..services.chamado_service import ChamadoService # Ensure import inside if needed to avoid circular, but top level is fine usually.
        ChamadoService.delete(id, current_user.id)
        flash('Chamado excluído com sucesso!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        flash(f'Erro ao excluir chamado: {str(e)}', 'danger')
        
    return redirect(url_for('operacional.chamados'))

@operacional_bp.route('/tecnicos/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def deletar_tecnico(id):
    try:
        from ..services.tecnico_service import TecnicoService
        TecnicoService.delete(id, current_user.id)
        flash('Técnico excluído com sucesso!', 'success')
        return redirect(url_for('operacional.tecnicos'))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('operacional.tecnico_detalhes', id=id))
    except Exception as e:
        flash(f'Erro ao excluir técnico: {str(e)}', 'danger')
        return redirect(url_for('operacional.tecnicos'))





# =============================================================================
# ATENDIMENTOS (INBOX DE VALIDAÇÃO POR LOTE)
# =============================================================================

@operacional_bp.route('/atendimentos')
@login_required
def atendimentos():
    """Inbox de lotes pendentes de validação"""
    batches = ChamadoService.get_pending_batches()
    return render_template('atendimentos.html', batches=batches)


@operacional_bp.route('/atendimentos/validar', methods=['POST'])
@login_required
def validar_atendimento():
    """Aprova ou rejeita um lote inteiro de chamados"""
    try:
        batch_id = request.form.get('batch_id')
        acao = request.form.get('acao')
        motivo = request.form.get('motivo', '').strip()
        
        if not batch_id:
            flash('Lote não identificado.', 'danger')
            return redirect(url_for('operacional.atendimentos'))
        
        if acao == 'aprovar':
            count = ChamadoService.aprovar_batch(batch_id, current_user.id)
            flash(f'✅ Lote aprovado! {count} chamado(s) liberados para o Financeiro.', 'success')
        elif acao == 'rejeitar':
            if not motivo or len(motivo) < 10:
                flash('O motivo da rejeição deve ter no mínimo 10 caracteres.', 'danger')
                return redirect(url_for('operacional.atendimentos'))
            count = ChamadoService.rejeitar_batch(batch_id, current_user.id, motivo)
            flash(f'❌ Lote rejeitado. {count} chamado(s) excluídos e criadores notificados.', 'warning')
        else:
            flash('Ação inválida.', 'danger')
            
    except Exception as e:
        flash(f'Erro ao processar validação: {str(e)}', 'danger')
    
    return redirect(url_for('operacional.atendimentos'))


# =============================================================================
# NOTIFICAÇÕES
# =============================================================================

@operacional_bp.route('/notificacoes')
@login_required
def minhas_notificacoes():
    """Lista notificações do usuário"""
    from ..models import Notification
    
    notificacoes = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notificacoes.html', notificacoes=notificacoes)


@operacional_bp.route('/notificacoes/marcar-lidas', methods=['POST'])
@login_required
def marcar_notificacoes_lidas():
    """Marca todas as notificações como lidas"""
    from ..models import Notification, db
    
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    flash('Notificações marcadas como lidas.', 'success')
    return redirect(url_for('operacional.minhas_notificacoes'))


@operacional_bp.route('/notificacoes/<int:id>/ler', methods=['POST'])
@login_required
def ler_notificacao(id):
    """Marca uma notificação específica como lida"""
    from ..models import Notification, db
    
    notif = Notification.query.get_or_404(id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    
    return jsonify({'success': True})

# =============================================================================
# RELATÓRIOS
# =============================================================================

@operacional_bp.route('/relatorios/fechamento')
@login_required
def relatorio_fechamento():
    """Tela de Relatório de Fechamento por Contrato"""
    from datetime import datetime, date
    
    # Filtros
    cliente_id = request.args.get('cliente')
    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    estado = request.args.get('estado')
    
    # Defaults
    today = date.today()
    if not data_inicio_str:
        data_inicio = date(today.year, today.month, 1)
        data_inicio_str = data_inicio.strftime('%Y-%m-%d')
    else:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        
    if not data_fim_str:
        data_fim = today
        data_fim_str = data_fim.strftime('%Y-%m-%d')
    else:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        
    # Dados para dropdowns
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    report_data = None
    if cliente_id:
        report_data = ChamadoService.get_relatorio_faturamento(
            cliente_id, data_inicio, data_fim, estado
        )
        
    return render_template('relatorios/fechamento.html',
        clientes=clientes,
        estados=ESTADOS_BRASIL,
        report=report_data,
        filters={
            'cliente': int(cliente_id) if cliente_id else '',
            'inicio': data_inicio_str,
            'fim': data_fim_str,
            'estado': estado or ''
        }
    )

@operacional_bp.route('/relatorios/fechamento/exportar')
@login_required
def exportar_fechamento():
    """Exporta CSV do fechamento"""
    from datetime import datetime
    
    cliente_id = request.args.get('cliente')
    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    estado = request.args.get('estado')
    
    if not cliente_id or not data_inicio_str or not data_fim_str:
        flash('Filtros inválidos para exportação', 'danger')
        return redirect(url_for('operacional.relatorio_fechamento'))
        
    data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    
    report_data = ChamadoService.get_relatorio_faturamento(
        cliente_id, data_inicio, data_fim, estado
    )
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Header
    writer.writerow(['Data', 'Código FSA', 'Cidade', 'Estado', 'Serviço', 'Valor Ticket'])
    
    # Rows
    for item in report_data['itens']:
        writer.writerow([
            item['data'],
            item['codigo'],
            item['cidade'],
            item['estado'],
            item['servico'],
            str(item['valor']).replace('.', ',')
        ])
        
    # Footer
    writer.writerow([])
    writer.writerow(['', '', '', '', 'TOTAL GERAL', str(report_data['total_geral']).replace('.', ',')])
    
    filename = f"fechamento_contrato_{data_inicio_str}_{data_fim_str}.csv"
    
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )
