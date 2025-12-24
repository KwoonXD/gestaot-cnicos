from flask import Blueprint, jsonify
from flask_login import login_required
from ..services.chamado_service import ChamadoService
from ..models import Cliente

api_bp = Blueprint('api', __name__)

@api_bp.route('/dashboard/evolucao')
@login_required
def dashboard_evolucao():
    """
    Retorna os dados para o gráfico de evolução de custos e volume.
    Usado pelo Chart.js no dashboard.html.
    """
    try:
        stats = ChamadoService.get_evolution_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dados_contrato')
@login_required
def dados_contrato():
    """
    Retorna JSON estruturado com todos os Clientes, Tipos de Serviço e LPUs.
    Usado pelo formulário de chamados para popular selects dinamicamente.
    """
    try:
        clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
        return jsonify({
            'clientes': [c.to_dict() for c in clientes]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
