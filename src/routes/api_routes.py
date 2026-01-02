from flask import Blueprint, jsonify
from flask_login import login_required
from ..services.chamado_service import ChamadoService
from ..models import Cliente, Chamado, Tecnico, db
from sqlalchemy import func
from datetime import datetime

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


@api_bp.route('/dashboard/top_tecnicos_he')
@login_required
def top_tecnicos_he():
    """
    Retorna os 5 técnicos com maior soma de horas extras no mês atual.
    Para gráfico de barras horizontal: custo/ineficiência.
    """
    try:
        # Mês atual
        hoje = datetime.now()
        inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Query: soma de valor_horas_extras por técnico
        results = db.session.query(
            Tecnico.nome,
            func.sum(Chamado.valor_horas_extras).label('total_he'),
            func.sum(Chamado.horas_trabalhadas).label('total_horas')
        ).join(Chamado).filter(
            Chamado.data_atendimento >= inicio_mes.date(),
            Chamado.status_validacao == 'Aprovado'
        ).group_by(Tecnico.id).order_by(
            func.sum(Chamado.valor_horas_extras).desc()
        ).limit(5).all()
        
        return jsonify({
            'labels': [r.nome for r in results],
            'valores': [float(r.total_he or 0) for r in results],
            'horas': [float(r.total_horas or 0) for r in results]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboard/top_tecnicos_volume')
@login_required
def top_tecnicos_volume():
    """
    Retorna os 5 técnicos com maior contagem de chamados no mês atual.
    Para gráfico de rosca: produtividade.
    """
    try:
        # Mês atual
        hoje = datetime.now()
        inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Query: contagem de chamados por técnico
        results = db.session.query(
            Tecnico.nome,
            func.count(Chamado.id).label('total_chamados'),
            func.sum(Chamado.valor_receita_total).label('total_receita')
        ).join(Chamado).filter(
            Chamado.data_atendimento >= inicio_mes.date(),
            Chamado.status_validacao == 'Aprovado'
        ).group_by(Tecnico.id).order_by(
            func.count(Chamado.id).desc()
        ).limit(5).all()
        
        return jsonify({
            'labels': [r.nome for r in results],
            'valores': [int(r.total_chamados or 0) for r in results],
            'receitas': [float(r.total_receita or 0) for r in results]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
