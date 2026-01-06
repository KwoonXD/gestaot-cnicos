from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from ..models import db, ItemLPU, Tecnico, TecnicoStock, StockMovement
from ..services.stock_service import StockService
from ..services.tecnico_service import TecnicoService
from ..decorators import admin_required

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/controle')
@login_required
@admin_required
def controle_estoque():
    # 1. Carrega itens (Gerais - sem cliente específico ou todos se preferir)
    # Ajuste: Mostra itens gerais (cliente_id=None) para o almoxarifado central
    itens = ItemLPU.query.filter_by(cliente_id=None).order_by(ItemLPU.nome).all()
    
    # 2. Carrega Técnicos
    tecnicos = TecnicoService.get_all()
    
    # 3. Matriz de Estoque
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
    try:
        tipo = request.form.get('tipo_movimento')
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

# --- NOVAS ROTAS DE GESTÃO DE CATÁLOGO ---

@stock_bp.route('/item/adicionar', methods=['POST'])
@login_required
@admin_required
def adicionar_item():
    try:
        nome = request.form.get('nome')
        if not nome:
            flash('Nome do item é obrigatório.', 'warning')
            return redirect(url_for('stock.controle_estoque'))
            
        # Verifica duplicidade
        exists = ItemLPU.query.filter_by(nome=nome, cliente_id=None).first()
        if exists:
            flash(f'O item "{nome}" já existe.', 'warning')
            return redirect(url_for('stock.controle_estoque'))

        # Cria novo item (cliente_id=None indica item de estoque geral)
        novo_item = ItemLPU(nome=nome, valor_receita=0.0, cliente_id=None)
        db.session.add(novo_item)
        db.session.commit()
        flash(f'Item "{nome}" adicionado com sucesso!', 'success')
        
    except Exception as e:
        flash(f'Erro ao adicionar item: {str(e)}', 'danger')
        
    return redirect(url_for('stock.controle_estoque'))

@stock_bp.route('/item/<int:item_id>/deletar', methods=['POST'])
@login_required
@admin_required
def deletar_item(item_id):
    try:
        item = ItemLPU.query.get_or_404(item_id)
        
        # Verifica se há estoque em posse de alguém
        em_uso = TecnicoStock.query.filter_by(item_lpu_id=item_id).filter(TecnicoStock.quantidade > 0).first()
        
        if em_uso:
            flash(f'Não é possível excluir "{item.nome}". Há técnicos com saldo positivo deste item.', 'danger')
        else:
            db.session.delete(item)
            db.session.commit()
            flash(f'Item "{item.nome}" removido do catálogo.', 'success')
            
    except Exception as e:
        # Geralmente erro de Foreign Key se houver histórico antigo
        db.session.rollback()
        flash(f'Não foi possível excluir. O item pode ter histórico de movimentações.', 'warning')
        
    return redirect(url_for('stock.controle_estoque'))
