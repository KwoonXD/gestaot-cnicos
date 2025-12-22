from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
# CORREÇÃO AQUI: Importamos Chamado, Pagamento e Tecnico explicitamente
from ..models import ESTADOS_BRASIL, FORMAS_PAGAMENTO, Chamado, Pagamento, Tecnico
from ..services.tecnico_service import TecnicoService
from ..services.chamado_service import ChamadoService
from ..services.financeiro_service import FinanceiroService

operacional_bp = Blueprint('operacional', __name__)

STATUS_TECNICO = ['Ativo', 'Inativo']
TIPOS_SERVICO = ['Americanas', 'Escolas', 'Telmex', 'Telmex Urgente', 'Esteira']
STATUS_CHAMADO = ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']

@operacional_bp.route('/')
@login_required
def dashboard():
    tecnico_stats = TecnicoService.get_stats()
    chamado_stats = ChamadoService.get_dashboard_stats()
    financeiro_stats = FinanceiroService.get_pendentes_stats()
    
    return render_template('dashboard.html',
        total_tecnicos_ativos=tecnico_stats['ativos'],
        chamados_mes=chamado_stats['chamados_mes'],
        valor_total_pendente=tecnico_stats['total_pendente'],
        pagamentos_pendentes=financeiro_stats,
        chamados_por_status=chamado_stats['chamados_por_status'],
        ultimos_chamados=chamado_stats['ultimos']
    )

@operacional_bp.route('/tecnicos')
@login_required
def tecnicos():
    filters = {
        'estado': request.args.get('estado', ''),
        'cidade': request.args.get('cidade', ''),
        'status': request.args.get('status', ''),
        'pagamento': request.args.get('pagamento', ''),
        'search': request.args.get('search', '')
    }
    
    tecnicos_list = TecnicoService.get_all(filters)
    
    # Get states for dropdown
    estados_usados = sorted(list(set([t.estado for t in tecnicos_list if t.estado])))
    
    return render_template('tecnicos.html',
        tecnicos=tecnicos_list,
        estados=ESTADOS_BRASIL,
        estados_usados=estados_usados,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        estado_filter=filters['estado'],
        cidade_filter=filters['cidade'],
        status_filter=filters['status'],
        pagamento_filter=filters['pagamento'],
        search=filters['search']
    )

@operacional_bp.route('/tecnicos/novo', methods=['GET', 'POST'])
@login_required
def novo_tecnico():
    if request.method == 'POST':
        TecnicoService.create(request.form)
        return redirect(url_for('operacional.tecnicos'))
    
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
        TecnicoService.update(id, request.form)
        return redirect(url_for('operacional.tecnico_detalhes', id=id))
    
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
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', ''),
        'tipo': request.args.get('tipo', ''),
        'pago': request.args.get('pago', '')
    }
    
    chamados_list = ChamadoService.get_all(filters)
    tecnicos_list = TecnicoService.get_all({'status': 'Ativo'})
    
    return render_template('chamados.html',
        chamados=chamados_list,
        tecnicos=tecnicos_list,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO,
        tecnico_filter=filters['tecnico_id'],
        status_filter=filters['status'],
        tipo_filter=filters['tipo'],
        pago_filter=filters['pago']
    )

@operacional_bp.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    if request.method == 'POST':
        ChamadoService.create(request.form)
        return redirect(url_for('operacional.chamados'))
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=None,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    chamado = ChamadoService.get_by_id(id)
    
    if request.method == 'POST':
        ChamadoService.update(id, request.form)
        return redirect(url_for('operacional.chamados'))
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=chamado,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status_chamado(id):
    ChamadoService.update_status(id, request.form.get('status'))
    return redirect(url_for('operacional.chamados'))
