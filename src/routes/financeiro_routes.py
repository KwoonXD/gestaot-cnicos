from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime
from ..services.financeiro_service import FinanceiroService
from ..services.tecnico_service import TecnicoService
from ..models import ESTADOS_BRASIL, Chamado, Lancamento

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
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', '')
    }
    
    sort_by = request.args.get('sort_by', 'nome_asc')
    
    pagamentos_list = FinanceiroService.get_all(filters)
    tecnicos_list = TecnicoService.get_all()
    tecnicos_com_pendente = [t for t in tecnicos_list if t.total_a_pagar > 0]
    
    # Sorting Logic
    if sort_by == 'nome_asc':
        tecnicos_com_pendente.sort(key=lambda t: t.nome)
    elif sort_by == 'valor_desc':
        tecnicos_com_pendente.sort(key=lambda t: t.total_a_pagar, reverse=True)
    elif sort_by == 'antiguidade':
        # Sort by oldest service date (None values last)
        tecnicos_com_pendente.sort(key=lambda t: t.oldest_pending_atendimento or datetime.max.date())
    elif sort_by == 'recente':
        # Sort by newest service date
        tecnicos_com_pendente.sort(key=lambda t: t.newest_pending_atendimento or datetime.min.date(), reverse=True)
    elif sort_by == 'upload_antigo':
        # Sort by oldest upload (creation) date
        tecnicos_com_pendente.sort(key=lambda t: t.oldest_pending_criacao or datetime.max)
    elif sort_by == 'upload_recente':
        # Sort by newest upload (creation) date
        tecnicos_com_pendente.sort(key=lambda t: t.newest_pending_criacao or datetime.min, reverse=True)
    
    return render_template('pagamentos.html',
        pagamentos=pagamentos_list,
        tecnicos=tecnicos_list,
        tecnicos_com_pendente=tecnicos_com_pendente,
        status_filter=filters['status'],
        current_sort=sort_by
    )

@financeiro_bp.route('/pagamentos/gerar', methods=['GET', 'POST'])
@login_required
def gerar_pagamento():
    if request.method == 'POST':
        pagamento, error = FinanceiroService.gerar_pagamento(request.form)
        if error:
            # Em caso de erro, recarregamos a lista filtrada
            todos_tecnicos = TecnicoService.get_all() # Assuming get_all returns list, if pagination, need .items or unpaginated
            # Actually TecnicoService.get_all() returns pagination object if no args? No, looking at service:
            # get_all(filters=None, page=1, per_page=20) returns pagination.
            # But the existing code was: tecnicos = [t for t in TecnicoService.get_all() if t.total_a_pagar > 0]
            # This implies get_all might return a query object or list depending on implementation?
            # Checking service: it returns query.order_by().paginate(). 
            # Wait, the previous code was: tecnicos = [t for t in TecnicoService.get_all({'status': 'Ativo'}) if t.total_a_pagar > 0]
            # If get_all returns pagination, iteration works on .items usually?
            # Let's fix this to be safe. We need a list of all active technicians.
            # Better to use Tecnico.query directly or a specific service method "get_all_list"
            # However, looking at previous code, it seems it was iterating the result of get_all(). 
            # Let's assume for now we need to fetch all active without pagination.
            # TecnicoService.get_all(filters={'status':'Ativo'}, page=1, per_page=1000).items
            
            # Using query directly for safety as per my knowledge of the service
            from ..models import Tecnico
            todos_tecnicos = Tecnico.query.filter_by(status='Ativo').all()
            
            tecnicos_display = [t for t in todos_tecnicos if t.tecnico_principal_id is None and t.total_agregado > 0]
            return render_template('pagamento_gerar.html', tecnicos=tecnicos_display, error=error)
        return redirect(url_for('financeiro.pagamentos'))
    
    # GET: Listar apenas CHEFES que têm valores a receber (próprio ou de subs)
    from ..models import Tecnico
    todos_tecnicos = Tecnico.query.filter_by(status='Ativo').all()
    
    tecnicos_display = []
    for t in todos_tecnicos:
        # Regra 1: Se tem chefe, não aparece na lista (o pagamento vai pro chefe)
        if t.tecnico_principal_id is not None:
            continue
            
        # Regra 2: Mostra se tiver algo a receber no total (Agregado)
        if t.total_agregado > 0:
            tecnicos_display.append(t)
            
    return render_template('pagamento_gerar.html', tecnicos=tecnicos_display, error=None)

@financeiro_bp.route('/pagamentos/<int:id>')
@login_required
def pagamento_detalhes(id):
    pagamento = FinanceiroService.get_by_id(id)
    return render_template('pagamento_detalhes.html',
        pagamento=pagamento,
        chamados=pagamento.chamados_incluidos.all()
    )

@financeiro_bp.route('/pagamentos/<int:id>/pagar', methods=['POST'])
@login_required
def marcar_como_pago(id):
    FinanceiroService.marcar_como_pago(id, request.form.get('observacoes', ''))
    return redirect(url_for('financeiro.pagamentos'))

@financeiro_bp.route('/fechamento', methods=['GET', 'POST'])
@login_required
def fechamento_lote():
    if request.method == 'POST':
        tecnicos_ids = request.form.getlist('tecnicos_ids')
        periodo_inicio = request.form.get('periodo_inicio')
        periodo_fim = request.form.get('periodo_fim')
        
        if not tecnicos_ids or not periodo_inicio or not periodo_fim:
            flash('Selecione técnicos e o período corretamente.', 'danger')
            return redirect(url_for('financeiro.fechamento_lote'))
            
        dados_lote = {
            'tecnicos_ids': [int(id) for id in tecnicos_ids],
            'periodo_inicio': periodo_inicio,
            'periodo_fim': periodo_fim
        }
        
        # Chama o serviço (que agora é assíncrono)
        FinanceiroService.gerar_pagamento_lote(dados_lote)
        
        # Feedback adaptado
        flash(f'O processamento de {len(tecnicos_ids)} técnicos foi iniciado em segundo plano. Atualize a página em instantes.', 'info')
                
        return redirect(url_for('financeiro.pagamentos'))

    # GET
    periodo_inicio = request.args.get('inicio', '')
    periodo_fim = request.args.get('fim', '')
    
    # Logic to show technicians with pending amounts in the period?
    # Or just show all active technicians and let user select?
    # Requirement: "No topo, filtros de data (Início/Fim) e um botão 'Filtrar'."
    # "A Tabela: ... Técnico, Qtd Chamados, Total Previsto (R$)."
    
    tecnicos_display = []
    
    # Only calculate if we have dates, otherwise show empty or all?
    # Let's show all active if no date, or empty. Usually filtering is needed first.
    if periodo_inicio and periodo_fim:
        # We need a way to get "preview" of payment for each tecnico
        # optimize this query in real app
        tecnicos_ativos = TecnicoService.get_all({'status': 'Ativo'})
        for t in tecnicos_ativos:
            # We can reuse logic or create a lightweight service method for preview
            # For now, let's just query chamados count/sum for this period per tecnico
            # This is N+1 but acceptable for <100 techs.
            # TODO: Add Service method for Preview Batch
            chamados_periodo = t.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.pago == False,
                Chamado.pagamento_id == None,
                Chamado.data_atendimento >= datetime.strptime(periodo_inicio, '%Y-%m-%d').date(),
                Chamado.data_atendimento <= datetime.strptime(periodo_fim, '%Y-%m-%d').date()
            ).all()
            
            lancamentos_list = Lancamento.query.filter(
                Lancamento.tecnico_id == t.id,
                Lancamento.pagamento_id == None,
                Lancamento.data <= datetime.strptime(periodo_fim, '%Y-%m-%d').date()
            ).all()

            qtd = len(chamados_periodo)
            total_chamados = sum(c.valor for c in chamados_periodo)
            total_lancamentos = sum(l.valor if l.tipo == 'Bônus' else -l.valor for l in lancamentos_list)
            
            total_previsto = float(total_chamados) + float(total_lancamentos)
            
            if qtd > 0 or total_lancamentos != 0:
                tecnicos_display.append({
                    'id': t.id,
                    'id_tecnico': t.id_tecnico,
                    'nome': t.nome,
                    'qtd_chamados': qtd,
                    'total_previsto': total_previsto
                })

    return render_template('fechamento_lote.html', 
                           tecnicos=tecnicos_display,
                           inicio=periodo_inicio,
                           fim=periodo_fim)

@financeiro_bp.route('/lancamentos/novo', methods=['POST'])
@login_required
def novo_lancamento():
    try:
        FinanceiroService.criar_lancamento(request.form)
        flash('Lançamento adicionado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar lançamento: {str(e)}', 'danger')
        
    # Redirect back to tecnico details
    return redirect(url_for('operacional.tecnico_detalhes', id=request.form['tecnico_id']))
