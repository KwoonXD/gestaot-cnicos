from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required
from ..services.chamado_service import ChamadoService
from ..models import Cliente, Chamado, Tecnico, db, TecnicoStock, ItemLPU, Pagamento
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

# --- Feature B: Endpoint de Estoque ---
@api_bp.route('/estoque/tecnico/<int:id>', methods=['GET'])
@login_required
def get_estoque_tecnico(id):
    """
    Retorna o saldo de peças que está com o técnico.
    Retorno: { 'id_item_lpu': quantidade, ... }
    """
    try:
        stock_items = TecnicoStock.query.filter_by(tecnico_id=id).all()
        # Retorna dicionário { item_id: qtd } para lookup rápido no JS
        saldo = {item.item_lpu_id: item.quantidade for item in stock_items}
        return jsonify(saldo)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pagamentos/<int:id>')
@login_required
def get_pagamento_detalhes(id):
    """
    Retorna detalhes completos de um pagamento histórico.
    Substitui a antiga página pagamento_detalhes.html.
    """
    try:
        pagamento = Pagamento.query.get_or_404(id)
        
        # Calcular totais para cards de rentabilidade
        chamados = pagamento.chamados_incluidos.all()
        receita_estimada = sum(float(c.valor_receita_total or 0) for c in chamados)
        lucro_bruto = receita_estimada - float(pagamento.valor_total)
        
        chamados_data = []
        for c in chamados:
            chamados_data.append({
                'data': c.data_atendimento.strftime('%d/%m/%Y'),
                'codigo': c.codigo_chamado or f"ID: {c.id}",
                'fsa_codes': c.fsa_codes or '',
                'tipo': c.tipo_servico,
                'endereco': f"{c.cidade or ''}",
                'valor_pago': float(c.custo_atribuido or c.valor),
                'status': c.status_chamado
            })
            
        return jsonify({
            'id': pagamento.id,
            'id_pagamento': pagamento.id_pagamento,
            'tecnico': {
                'id': pagamento.tecnico.id,
                'nome': pagamento.tecnico.nome,
                'id_tecnico': pagamento.tecnico.id_tecnico
            },
            'financeiro': {
                'valor_total': float(pagamento.valor_total),
                'receita_estimada': receita_estimada,
                'lucro_bruto': lucro_bruto,
                'margem_percentual': (lucro_bruto / receita_estimada * 100) if receita_estimada > 0 else 0
            },
            'info': {
                'data_pagamento': pagamento.data_pagamento.strftime('%d/%m/%Y') if pagamento.data_pagamento else None,
                'periodo': f"{pagamento.periodo_inicio.strftime('%d/%m/%Y')} - {pagamento.periodo_fim.strftime('%d/%m/%Y')}",
                'status': pagamento.status_pagamento,
                'observacoes': pagamento.observacoes,
                'comprovante_url': url_for('static', filename=pagamento.comprovante_path) if pagamento.comprovante_path else None
            },
            'chamados': chamados_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
