from flask import Blueprint, jsonify
from flask_login import login_required
from ..services.tecnico_service import TecnicoService
from ..services.chamado_service import ChamadoService
from ..services.financeiro_service import FinanceiroService

api_bp = Blueprint('api', __name__)

@api_bp.route('/tecnicos')
@login_required
def api_tecnicos():
    tecnicos = TecnicoService.get_all()
    return jsonify([t.to_dict() for t in tecnicos])

@api_bp.route('/chamados')
@login_required
def api_chamados():
    chamados = ChamadoService.get_all()
    return jsonify([c.to_dict() for c in chamados])

@api_bp.route('/pagamentos')
@login_required
def api_pagamentos():
    pagamentos = FinanceiroService.get_all()
    return jsonify([p.to_dict() for p in pagamentos])

@api_bp.route('/dashboard')
@login_required
def api_dashboard():
    # Reuse logical gathering or creating a specialized API DTO service if needed.
    # For now, replicate logic from dashboard but returning dict
    tecnico_stats = TecnicoService.get_stats()
    chamado_stats = ChamadoService.get_dashboard_stats()
    financeiro_stats = FinanceiroService.get_pendentes_stats()
    
    return jsonify({
        'total_tecnicos_ativos': tecnico_stats['ativos'],
        'chamados_mes': chamado_stats['chamados_mes'],
        'valor_total_pendente': tecnico_stats['total_pendente'],
        'pagamentos_pendentes': financeiro_stats,
        'chamados_por_status': chamado_stats['chamados_por_status']
    })
