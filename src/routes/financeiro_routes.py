from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime
from ..services.financeiro_service import FinanceiroService
from ..services.tecnico_service import TecnicoService
from ..models import ESTADOS_BRASIL, Chamado, Lancamento

financeiro_bp = Blueprint('financeiro', __name__)

STATUS_PAGAMENTO = ['Pendente', 'Pago', 'Cancelado']

@financeiro_bp.route('/pagamentos')
@login_required
def pagamentos():
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', '')
    }
    
    pagamentos_list = FinanceiroService.get_all(filters)
    tecnicos_list = TecnicoService.get_all()
    tecnicos_com_pendente = [t for t in tecnicos_list if t.total_a_pagar > 0]
    
    return render_template('pagamentos.html',
        pagamentos=pagamentos_list,
        tecnicos=tecnicos_list,
        tecnicos_com_pendente=tecnicos_com_pendente,
        status_options=STATUS_PAGAMENTO,
        tecnico_filter=filters['tecnico_id'],
        status_filter=filters['status']
    )

@financeiro_bp.route('/pagamentos/gerar', methods=['GET', 'POST'])
@login_required
def gerar_pagamento():
    if request.method == 'POST':
        pagamento, error = FinanceiroService.gerar_pagamento(request.form)
        if error:
            tecnicos = [t for t in TecnicoService.get_all() if t.total_a_pagar > 0]
            return render_template('pagamento_gerar.html', tecnicos=tecnicos, error=error)
        return redirect(url_for('financeiro.pagamentos'))
    
    tecnicos = [t for t in TecnicoService.get_all({'status': 'Ativo'}) if t.total_a_pagar > 0]
    return render_template('pagamento_gerar.html', tecnicos=tecnicos, error=None)

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
        # Expecting form data with list of tecnicos and date range
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
        
        count, errors = FinanceiroService.gerar_pagamento_lote(dados_lote)
        
        if count > 0:
            flash(f'{count} pagamentos gerados com sucesso!', 'success')
        
        if errors:
            for erro in errors:
                flash(erro, 'warning') # Show as warnings
                
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
