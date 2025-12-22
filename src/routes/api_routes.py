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

@api_bp.route('/tecnicos/<int:id>/pendencias')
@login_required
def api_tecnico_pendencias(id):
    tecnico = TecnicoService.get_by_id(id)
    if not tecnico:
        return jsonify({'error': 'Técnico não encontrado'}), 404
        
    pendencias = TecnicoService.get_pendencias(id)
    
    # Format response for the frontend
    response = {
        'tecnico': {
            'id': tecnico.id,
            'nome': tecnico.nome,
            'chave_pagamento': tecnico.chave_pagamento,
            'forma_pagamento': tecnico.forma_pagamento
        },
        'total_pendente': float(sum(c.valor for c in pendencias)),
        'chamados': [{
            'data': c.data_atendimento.strftime('%d/%m/%Y'),
            'codigo': c.codigo_chamado or str(c.id),
            'tipo': c.tipo_servico,
            'endereco': c.localizacao,
            'valor': float(c.valor)
        } for c in pendencias]
    }
    
    return jsonify(response)

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
