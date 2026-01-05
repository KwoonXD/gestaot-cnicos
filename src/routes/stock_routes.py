from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from ..services.stock_service import StockService
from ..services.tecnico_service import TecnicoService
from ..models import ItemLPU, TecnicoStock, Tecnico
from ..decorators import admin_required

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/painel')
@login_required
@admin_required
def controle_estoque():
    """Painel Geral de Estoque"""
    tecnicos = TecnicoService.get_all()
    # Para o dropdown de peças
    itens_lpu = ItemLPU.query.order_by(ItemLPU.nome).all()
    
    # Overview de estoque (opcional: mostrar tabela grande)
    # Por enquanto, mostramos apenas o formulário e talvez uma lista consolidada via AJAX ou na view
    
    return render_template('stock_control.html', tecnicos=tecnicos, itens=itens_lpu)

@stock_bp.route('/transferir', methods=['POST'])
@login_required
@admin_required
def transferir():
    try:
        tecnico_id = request.form.get('tecnico_id')
        item_id = request.form.get('item_id')
        quantidade = int(request.form.get('quantidade', 0))
        observacao = request.form.get('observacao')
        
        StockService.transferir_para_tecnico(item_id, tecnico_id, quantidade, current_user.id, observacao)
        flash('Transferência realizada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro na transferência: {str(e)}', 'danger')
        
    return redirect(url_for('stock.painel'))

@stock_bp.route('/tecnico/<int:tecnico_id>/api')
@login_required
def get_tecnico_stock_api(tecnico_id):
    """API para retornar estoque JSON do técnico"""
    estoque = StockService.get_stock_by_tecnico(tecnico_id)
    payload = [e.to_dict() for e in estoque if e.quantidade > 0]
    return jsonify(payload)

@stock_bp.route('/devolver', methods=['POST'])
@login_required
def devolver_peca():
    """Rota para técnico ou admin registrar devolução"""
    # ... Implementation if needed
    pass
