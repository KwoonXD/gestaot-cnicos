from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from ..models import db, ItemLPU, Tecnico, TecnicoStock, StockMovement
from ..services.stock_service import StockService
from ..decorators import admin_required

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/controle')
@login_required
@admin_required
def controle_estoque():
    # 1. Carrega dados para a UI
    itens = ItemLPU.query.filter_by(cliente_id=None).order_by(ItemLPU.nome).all() 
    # Fallback se não usar a convenção de cliente_id=None para itens gerais
    if not itens:
        itens = ItemLPU.query.order_by(ItemLPU.nome).all()
        
    tecnicos = TecnicoService.get_all() # Reusing helper to get sorted tecnicos with attributes if needed
    
    # 2. Matriz de Estoque: { tecnico_id: { item_id: qtd } }
    stock_data = TecnicoStock.query.all()
    matrix = {}
    for s in stock_data:
        if s.tecnico_id not in matrix:
            matrix[s.tecnico_id] = {}
        matrix[s.tecnico_id][s.item_lpu_id] = s.quantidade

    return render_template('stock_control.html', 
        itens=itens, 
        tecnicos=tecnicos,
        matrix=matrix
    )

@stock_bp.route('/movimentar', methods=['POST'])
@login_required
@admin_required
def movimentar_estoque():
    """
    Processa movimentações rápidas:
    - ENVIO: Sede -> Técnico (Aumenta saldo técnico)
    - DEVOLUCAO: Técnico -> Sede (Diminui saldo técnico)
    - AJUSTE: Correção manual (Define saldo exato)
    """
    try:
        tipo = request.form.get('tipo_movimento') # 'ENVIO', 'DEVOLUCAO', 'AJUSTE'
        tecnico_id = request.form.get('tecnico_id')
        item_id = request.form.get('item_id')
        qtd = int(request.form.get('quantidade', 0))
        obs = request.form.get('observacao')

        if not all([tipo, tecnico_id, item_id, qtd]):
            flash('Dados incompletos.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        if tipo == 'ENVIO':
            StockService.transferir_sede_para_tecnico(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'✅ Enviado {qtd}un para o técnico.', 'success')
            
        elif tipo == 'DEVOLUCAO':
            StockService.devolver_tecnico_para_sede(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'✅ Recebido {qtd}un do técnico.', 'info')
            
        elif tipo == 'AJUSTE':
            StockService.ajustar_saldo(tecnico_id, item_id, qtd, current_user.id, obs)
            flash(f'⚠️ Saldo ajustado para {qtd}un.', 'warning')

    except Exception as e:
        flash(f'Erro na movimentação: {str(e)}', 'danger')

    return redirect(url_for('stock.controle_estoque'))

# Keep this for compatibility if frontend uses it (it shouldn't, but safe to keep)
@stock_bp.route('/tecnico/<int:tecnico_id>/api')
@login_required
def get_tecnico_stock_api(tecnico_id):
    estoque = StockService.get_stock_by_tecnico(tecnico_id)
    payload = [e.to_dict() for e in estoque if e.quantidade > 0]
    return jsonify(payload)

# Helper import inside to avoid circular deps if needed, or top level
from ..services.tecnico_service import TecnicoService
