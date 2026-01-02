from flask import Blueprint, jsonify, request
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


@api_bp.route('/tecnicos/<int:id>/pendencias')
@login_required
def tecnicos_pendencias(id):
    """
    Retorna os detalhes de pendências financeiras de um técnico específico.
    Usado pelo modal 'Visualizar e Pagar' em pagamentos.html.
    """
    try:
        tecnico = Tecnico.query.get_or_404(id)
        
        # Filtra chamados pendentes seguindo a regra rigorosa do Financeiro
        chamados = Chamado.query.filter(
            Chamado.tecnico_id == id,
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.status_validacao == 'Aprovado',
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ).order_by(Chamado.data_atendimento).all()
        
        chamados_data = []
        total_pendente = 0.0
        
        for c in chamados:
            valor = float(c.custo_atribuido or 0.0)
            total_pendente += valor
            
            chamados_data.append({
                'data': c.data_atendimento.strftime('%d/%m/%Y'),
                'codigo': c.codigo_chamado or f"ID: {c.id}",
                'fsa_codes': c.fsa_codes or '',
                'tipo': c.tipo_servico or 'N/A',
                'endereco': f"{c.cidade or ''}",
                'valor': valor
            })
            
        return jsonify({
            'tecnico': {
                'id': tecnico.id,
                'nome': tecnico.nome,
                'chave_pagamento': tecnico.chave_pagamento or 'Não cadastrada', 
                'forma_pagamento': tecnico.forma_pagamento or 'N/A'
            },
            'total_pendente': total_pendente,
            'chamados': chamados_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/importar/analisar', methods=['POST'])
@login_required
def analisar_importacao():
    """
    Recebe um arquivo e retorna o preview da análise.
    """
    from ..services.import_service import ImportService
    
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Arquivo vazio'}), 400
        
    result = ImportService.analisar_arquivo(file)
    return jsonify(result)
