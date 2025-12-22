from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..services.financeiro_service import FinanceiroService
from ..services.tecnico_service import TecnicoService
from ..models import ESTADOS_BRASIL # If needed

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
