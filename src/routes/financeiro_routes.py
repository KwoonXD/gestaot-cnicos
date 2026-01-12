from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required
from datetime import datetime
from ..services.financeiro_service import FinanceiroService
from ..services.tecnico_service import TecnicoService, TecnicoMetricas
from ..models import ESTADOS_BRASIL, Chamado, Tecnico
from werkzeug.utils import secure_filename
import os

from ..decorators import admin_required

financeiro_bp = Blueprint('financeiro', __name__)

@financeiro_bp.before_request
@login_required
@admin_required
def before_request():
    pass

STATUS_PAGAMENTO = ['Pendente', 'Pago', 'Cancelado']

@financeiro_bp.route('/pagamentos')
@login_required
def pagamentos():
    """
    Lista pagamentos e tecnicos com pendencias.
    OTIMIZADO: Usa get_tecnicos_com_metricas() para evitar N+1 queries.
    """
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', '')
    }

    sort_by = request.args.get('sort_by', 'nome_asc')

    pagamentos_list = FinanceiroService.get_all(filters)

    # OTIMIZACAO: Usar get_tecnicos_com_metricas() diretamente
    # Isso retorna TecnicoMetricas com todas as agregacoes pre-calculadas
    result = TecnicoService.get_tecnicos_com_metricas(page=None)
    metricas_list = result['items']  # Lista de TecnicoMetricas

    # Filtrar apenas tecnicos com pendencias (usando metricas pre-calculadas)
    tecnicos_com_pendente = [m for m in metricas_list if m.total_a_pagar_agregado > 0]

    # Lista completa para dropdown (objetos Tecnico)
    tecnicos_list = [m.tecnico for m in metricas_list]

    # Sorting Logic (usando atributos do TecnicoMetricas)
    if sort_by == 'nome_asc':
        tecnicos_com_pendente.sort(key=lambda m: m.nome)
    elif sort_by == 'valor_desc':
        tecnicos_com_pendente.sort(key=lambda m: m.total_a_pagar_agregado, reverse=True)
    elif sort_by == 'antiguidade':
        # Sort by oldest service date (None values last)
        tecnicos_com_pendente.sort(key=lambda m: m.oldest_pending_date or datetime.max.date())
    elif sort_by == 'recente':
        # Sort by newest service date
        tecnicos_com_pendente.sort(key=lambda m: m.newest_pending_date or datetime.min.date(), reverse=True)
    elif sort_by == 'upload_antigo':
        # Fallback para oldest_pending_date (criacao nao esta nas metricas otimizadas)
        tecnicos_com_pendente.sort(key=lambda m: m.oldest_pending_date or datetime.max.date())
    elif sort_by == 'upload_recente':
        tecnicos_com_pendente.sort(key=lambda m: m.newest_pending_date or datetime.min.date(), reverse=True)

    return render_template('pagamentos.html',
        pagamentos=pagamentos_list,
        tecnicos=tecnicos_list,
        tecnicos_com_pendente=tecnicos_com_pendente,
        status_filter=filters['status'],
        current_sort=sort_by
    )

@financeiro_bp.route('/pagamentos/exportar-pix-lote', methods=['POST'])
@login_required
def exportar_pix_lote():
    """
    Gera arquivo TXT com dados de pagamento para lote.
    OTIMIZADO: Usa get_tecnicos_com_metricas() para evitar N+1 queries.
    """
    try:
        tecnicos_ids = request.form.getlist('tecnicos_ids')
        if not tecnicos_ids:
            flash('Nenhum tecnico selecionado.', 'warning')
            return redirect(url_for('financeiro.pagamentos'))

        # OTIMIZACAO: Usar get_tecnicos_com_metricas()
        result = TecnicoService.get_tecnicos_com_metricas(page=None)
        metricas_map = {str(m.tecnico.id): m for m in result['items']}

        # Filter only selected IDs
        tecnicos_ids_str = set(tecnicos_ids)

        output_lines = []
        total_geral = 0.0

        output_lines.append(f"LOTE DE PAGAMENTOS - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        output_lines.append("="*50 + "\n")

        for tid in tecnicos_ids_str:
            m = metricas_map.get(tid)
            if not m or m.total_a_pagar_agregado <= 0:
                continue

            t = m.tecnico
            valor = m.total_a_pagar_agregado
            chave_pix = t.chave_pagamento if t.chave_pagamento else "CHAVE NAO CADASTRADA"
            doc = t.documento if t.documento else "CPF NAO CADASTRADO"

            total_geral += valor

            output_lines.append(f"NOME: {t.nome.upper()}")
            output_lines.append(f"CPF/CNPJ: {doc}")
            output_lines.append(f"VALOR: R$ {valor:.2f}")
            output_lines.append(f"PIX: {chave_pix}")
            output_lines.append("-" * 40 + "\n")

        output_lines.append("="*50)
        output_lines.append(f"TOTAL DO LOTE: R$ {total_geral:.2f}")

        content = "\n".join(output_lines)

        return Response(
            content,
            mimetype="text/plain",
            headers={"Content-disposition": f"attachment; filename=pix_lote_{datetime.now().strftime('%Y%m%d')}.txt"}
        )

    except Exception as e:
        flash(f'Erro ao gerar lote: {str(e)}', 'danger')
        return redirect(url_for('financeiro.pagamentos'))

@financeiro_bp.route('/pagamentos/gerar', methods=['GET', 'POST'])
@login_required
def gerar_pagamento():
    """
    Gera pagamento para tecnico(s).
    OTIMIZADO: Usa get_tecnicos_com_metricas() para evitar N+1 queries.
    """
    if request.method == 'POST':
        pagamento, error = FinanceiroService.gerar_pagamento(request.form)
        if error:
            # Em caso de erro, recarregamos a lista filtrada
            result = TecnicoService.get_tecnicos_com_metricas(
                filters={'status': 'Ativo'},
                page=None
            )
            tecnicos_display = [
                m for m in result['items']
                if m.tecnico.tecnico_principal_id is None and m.total_a_pagar_agregado > 0
            ]
            return render_template('pagamento_gerar.html', tecnicos=tecnicos_display, error=error)
        return redirect(url_for('financeiro.pagamentos'))

    # GET: Listar apenas CHEFES que tem valores a receber (proprio ou de subs)
    result = TecnicoService.get_tecnicos_com_metricas(
        filters={'status': 'Ativo'},
        page=None
    )

    # Filtrar: apenas tecnicos principais com valores pendentes
    tecnicos_display = [
        m for m in result['items']
        if m.tecnico.tecnico_principal_id is None and m.total_a_pagar_agregado > 0
    ]

    return render_template('pagamento_gerar.html', tecnicos=tecnicos_display, error=None)



@financeiro_bp.route('/pagamentos/<int:id>/pagar', methods=['POST'])
@login_required
def marcar_como_pago(id):
    import os
    from flask import current_app
    
    pagamento = FinanceiroService.get_by_id(id)
    observacoes = request.form.get('observacoes', '')
    
    if 'comprovante' in request.files:
        file = request.files['comprovante']
        if file and file.filename != '':
            filename = secure_filename(f"comprovante_{pagamento.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            upload_folder = os.path.join(current_app.static_folder, 'uploads', 'comprovantes')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            pagamento.comprovante_path = f"uploads/comprovantes/{filename}"
    
    FinanceiroService.marcar_como_pago(id, observacoes)
    return redirect(url_for('financeiro.pagamentos'))

@financeiro_bp.route('/fechamento', methods=['GET', 'POST'])
@login_required
def fechamento_lote():
    """
    Fechamento de pagamentos em lote por periodo.
    OTIMIZADO: Usa query SQL agregada para evitar N+1.
    """
    from sqlalchemy import func, case, and_

    if request.method == 'POST':
        tecnicos_ids = request.form.getlist('tecnicos_ids')
        periodo_inicio = request.form.get('periodo_inicio')
        periodo_fim = request.form.get('periodo_fim')

        if not tecnicos_ids or not periodo_inicio or not periodo_fim:
            flash('Selecione tecnicos e o periodo corretamente.', 'danger')
            return redirect(url_for('financeiro.fechamento_lote'))

        dados_lote = {
            'tecnicos_ids': [int(id) for id in tecnicos_ids],
            'periodo_inicio': periodo_inicio,
            'periodo_fim': periodo_fim
        }

        FinanceiroService.gerar_pagamento_lote(dados_lote)
        flash(f'O processamento de {len(tecnicos_ids)} tecnicos foi iniciado em segundo plano. Atualize a pagina em instantes.', 'info')
        return redirect(url_for('financeiro.pagamentos'))

    periodo_inicio = request.args.get('inicio', '')
    periodo_fim = request.args.get('fim', '')
    tecnicos_display = []

    if periodo_inicio and periodo_fim:
        data_inicio = datetime.strptime(periodo_inicio, '%Y-%m-%d').date()
        data_fim = datetime.strptime(periodo_fim, '%Y-%m-%d').date()

        # OTIMIZACAO: Query SQL agregada em vez de N+1
        # REFATORADO: Removido fallback para Chamado.valor (campo DEPRECATED)
        val_expr = func.coalesce(Chamado.custo_atribuido, 0)

        from ..models import db

        result = db.session.query(
            Tecnico.id,
            Tecnico.nome,
            func.count(Chamado.id).label('qtd_chamados'),
            func.sum(val_expr).label('total_previsto')
        ).join(
            Chamado, Tecnico.id == Chamado.tecnico_id
        ).filter(
            Tecnico.status == 'Ativo',
            Chamado.status_chamado == 'Concluído',
            Chamado.pago == False,
            Chamado.pagamento_id == None,
            Chamado.data_atendimento >= data_inicio,
            Chamado.data_atendimento <= data_fim
        ).group_by(
            Tecnico.id
        ).having(
            func.count(Chamado.id) > 0
        ).all()

        for row in result:
            tecnicos_display.append({
                'id': row[0],
                'id_tecnico': f"T-{str(row[0]).zfill(3)}",
                'nome': row[1],
                'qtd_chamados': row[2],
                'total_previsto': float(row[3] or 0)
            })

    return render_template('fechamento_lote.html',
                           tecnicos=tecnicos_display,
                           inicio=periodo_inicio,
                           fim=periodo_fim)

@financeiro_bp.route('/fechamento-cliente')
@login_required
def fechamento_cliente():
    from ..models import Cliente, Chamado, CatalogoServico, db
    from sqlalchemy.orm import joinedload
    import io
    import csv
    from flask import Response
    
    cliente_id = request.args.get('cliente_id', type=int)
    mes = request.args.get('mes', type=int, default=datetime.now().month)
    ano = request.args.get('ano', type=int, default=datetime.now().year)
    export_csv = request.args.get('export') == 'true'
    
    clientes = Cliente.query.filter_by(ativo=True).all()
    chamados = []
    total_receita = 0.0
    cliente_selecionado = None
    
    if cliente_id:
        cliente_selecionado = Cliente.query.get(cliente_id)
        query = Chamado.query.join(CatalogoServico).filter(
            CatalogoServico.cliente_id == cliente_id,
            db.extract('month', Chamado.data_atendimento) == mes,
            db.extract('year', Chamado.data_atendimento) == ano,
            Chamado.status_chamado == 'Concluído'
        ).options(joinedload(Chamado.tecnico), joinedload(Chamado.catalogo_servico))
        
        chamados = query.order_by(Chamado.data_atendimento).all()
        total_receita = sum(float(c.valor_receita_total or 0) for c in chamados)
        
        if export_csv:
            output = io.StringIO()
            writer = csv.writer(output, delimiter=';')
            writer.writerow(['Data', 'Loja/Cidade', 'Técnico', 'FSA / Código', 'Serviço', 'Peça', 'Receita (R$)'])
            for c in chamados:
                writer.writerow([
                    c.data_atendimento.strftime('%d/%m/%Y'),
                    f"{c.loja or ''} {c.cidade}",
                    c.tecnico.nome if c.tecnico else 'N/A',
                    c.codigo_chamado or '-',
                    c.tipo_servico,
                    c.peca_usada or '-',
                    f"{float(c.valor_receita_total or 0):.2f}".replace('.', ',')
                ])
            return Response(
                output.getvalue().encode('utf-8-sig'),
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename=fechamento_{cliente_selecionado.nome}_{mes}_{ano}.csv"}
            )
            
    return render_template('fechamento_cliente.html',
        clientes=clientes,
        chamados=chamados,
        total_receita=total_receita,
        mes_atual=mes,
        ano_atual=ano,
        cliente_id=cliente_id,
        cliente_selecionado=cliente_selecionado
    )



@financeiro_bp.route('/dashboard/geografico')
@login_required
def dashboard_geo():
    from ..services.report_service import ReportService
    from ..models import Cliente
    inicio_str = request.args.get('inicio', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    fim_str = request.args.get('fim', datetime.now().strftime('%Y-%m-%d'))
    cliente_id = request.args.get('cliente_id')
    inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
    fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
    dados = ReportService.rentabilidade_geografica(inicio, fim, cliente_id=int(cliente_id) if cliente_id else None)
    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('dashboard_geo.html', 
        dados=dados, 
        inicio=inicio_str, 
        fim=fim_str, 
        clientes=clientes,
        cliente_id=int(cliente_id) if cliente_id else None
    )
