from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from src.decorators import admin_required
from src.models import AuditLog, User, Cliente, TipoServico, ItemLPU, ContratoItem, db
from sqlalchemy import desc

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/auditoria')
@login_required
@admin_required
def auditoria():
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    model_name = request.args.get('model_name')
    
    query = AuditLog.query

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    if model_name:
        query = query.filter(AuditLog.model_name.ilike(f"%{model_name}%"))
        
    pagination = query.order_by(desc(AuditLog.timestamp)).paginate(page=page, per_page=20)
    
    users = User.query.all()
    
    return render_template('audit_logs.html', pagination=pagination, users=users, selected_model=model_name, selected_user=user_id)

# --- USER MANAGEMENT CRUD ---

@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    users = User.query.order_by(User.username).all()
    from src.models import db # ensuring access if needed or just rely on global if configured
    return render_template('admin_users_list.html', users=users)

@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def user_new():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if User.query.filter_by(username=username).first():
            from flask import flash
            flash('Nome de usuário já existe.', 'danger')
        else:
            new_user = User(username=username, role=role)
            new_user.set_password(password)
            from src.models import db
            db.session.add(new_user)
            db.session.commit()
            
            # Audit
            from flask_login import current_user
            audit = AuditLog(
                user_id=current_user.id,
                model_name='User',
                object_id=str(new_user.id),
                action='CREATE',
                changes=f"Created user {username} as {role}"
            )
            db.session.add(audit)
            db.session.commit()
            
            from flask import flash, redirect, url_for
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('admin.users_list'))
            
    return render_template('admin_user_form.html', user=None, title="Novo Usuário")

@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        role = request.form.get('role')
        password = request.form.get('password')
        
        from flask_login import current_user
        
        # Prevent self-demotion if desired, but mostly specific requirement is Delete self-protection.
        # Let's allow edit role but maybe warn? For now standard logic.
        
        changes = []
        if user.role != role:
            changes.append(f"Role: {user.role} -> {role}")
            user.role = role
            
        if password: # Only update if provided
            user.set_password(password)
            changes.append("Password updated")
            
        if changes:
            from src.models import db
            # Audit
            audit = AuditLog(
                user_id=current_user.id,
                model_name='User',
                object_id=str(user.id),
                action='UPDATE',
                changes=", ".join(changes)
            )
            db.session.add(audit)
            db.session.commit()
            
            from flask import flash, redirect, url_for
            flash('Usuário atualizado com sucesso.', 'success')
            return redirect(url_for('admin.users_list'))
        else:
            from flask import flash, redirect, url_for
            flash('Nenhuma alteração realizada.', 'info')
            return redirect(url_for('admin.users_list'))
            
    return render_template('admin_user_form.html', user=user, title="Editar Usuário")

@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def user_delete(id):
    user = User.query.get_or_404(id)
    from flask_login import current_user
    from flask import abort, flash, redirect, url_for
    
    if user.id == current_user.id:
        flash('Você não pode excluir a si mesmo.', 'danger')
        return redirect(url_for('admin.users_list'))
        
    from src.models import db
    
    # Audit before delete (or after? usually before to log who did it to whom)
    # But if we delete the user, object_id is just a string.
    audit = AuditLog(
        user_id=current_user.id,
        model_name='User',
        object_id=str(user.id),
        action='DELETE',
        changes=f"Deleted user {user.username}"
    )
    db.session.add(audit)
    
    db.session.delete(user)
    db.session.commit()
    
    flash('Usuário excluído com sucesso.', 'success')
    return redirect(url_for('admin.users_list'))


# =============================================================================
# GESTÃO DE CONTRATOS
# =============================================================================

@admin_bp.route('/contratos')
@login_required
@admin_required
def contratos():
    """Dashboard de gestão de clientes/contratos"""
    clientes = Cliente.query.order_by(Cliente.nome).all()

    # Buscar todas as peças únicas para o dropdown de seleção
    todos_itens_lpu = ItemLPU.query.order_by(ItemLPU.nome).all()

    # Montar dicionário de custos para referência no frontend
    # O custo serve apenas para tomada de decisão (não é preço de venda)
    custos_itens = {
        item.id: float(item.valor_custo or 0)
        for item in todos_itens_lpu
    }

    return render_template('admin_contratos.html',
        clientes=clientes,
        todos_itens_lpu=todos_itens_lpu,
        custos_itens=custos_itens
    )


@admin_bp.route('/contratos/novo', methods=['POST'])
@login_required
@admin_required
def novo_cliente():
    """Criar novo cliente/contrato"""
    nome = request.form.get('nome', '').strip()
    
    if not nome:
        flash('Nome do cliente é obrigatório.', 'danger')
        return redirect(url_for('admin.contratos'))
    
    if Cliente.query.filter_by(nome=nome).first():
        flash(f'Cliente "{nome}" já existe.', 'warning')
        return redirect(url_for('admin.contratos'))
    
    cliente = Cliente(nome=nome)
    db.session.add(cliente)
    db.session.commit()
    
    # Audit
    AuditLog.query  # Just to ensure model is loaded
    audit = AuditLog(
        user_id=current_user.id,
        model_name='Cliente',
        object_id=str(cliente.id),
        action='CREATE',
        changes=f'Criado cliente: {nome}'
    )
    db.session.add(audit)
    db.session.commit()
    
    flash(f'Cliente "{nome}" criado com sucesso!', 'success')
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/cliente/<int:id>/servicos', methods=['POST'])
@login_required
@admin_required

def adicionar_servico(id):
    """Adicionar tipo de serviço a um cliente"""
    cliente = Cliente.query.get_or_404(id)
    
    nome = request.form.get('nome', '').strip()
    valor_receita = request.form.get('valor', 0)
    valor_custo_tecnico = request.form.get('valor_custo_tecnico', 0)
    valor_adc_receita = request.form.get('valor_adicional_receita', 0)
    valor_adc_custo = request.form.get('valor_adicional_custo', 0)
    valor_he_receita = request.form.get('valor_hora_adicional_receita', 0)
    valor_he_custo = request.form.get('valor_hora_adicional_custo', 0)
    cobra_visita = request.form.get('cobra_visita', 'on') == 'on'
    
    if not nome:
        flash('Nome do serviço é obrigatório.', 'danger')
        return redirect(url_for('admin.contratos'))
    
    try:
        valor_receita = float(valor_receita)
        valor_custo_tecnico = float(valor_custo_tecnico)
        valor_adc_receita = float(valor_adc_receita)
        valor_adc_custo = float(valor_adc_custo)
        valor_he_receita = float(valor_he_receita)
        valor_he_custo = float(valor_he_custo)
    except:
        valor_receita = 0.0
        valor_custo_tecnico = 0.0
        valor_adc_receita = 0.0
        valor_adc_custo = 0.0
        valor_he_receita = 0.0
        valor_he_custo = 0.0
    
    servico = TipoServico(
        nome=nome,
        valor_receita=valor_receita,
        valor_custo_tecnico=valor_custo_tecnico,
        valor_adicional_receita=valor_adc_receita,
        valor_adicional_custo=valor_adc_custo,
        valor_hora_adicional_receita=valor_he_receita,
        valor_hora_adicional_custo=valor_he_custo,
        cliente_id=cliente.id,
        exige_peca=cobra_visita
    )
    db.session.add(servico)
    db.session.commit()
    
    flash(f'Serviço "{nome}" adicionado ao cliente {cliente.nome}!', 'success')
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/cliente/<int:id>/lpu', methods=['POST'])
@login_required
@admin_required
def adicionar_lpu(id):
    """Adicionar item LPU a um cliente"""
    cliente = Cliente.query.get_or_404(id)
    
    nome = request.form.get('nome', '').strip()
    valor = request.form.get('valor', 0)
    
    if not nome:
        flash('Nome do item LPU é obrigatório.', 'danger')
        return redirect(url_for('admin.contratos'))
    
    try:
        valor = float(valor)
    except:
        valor = 0.0
    
    item = ItemLPU(
        nome=nome,
        valor_receita=valor,
        cliente_id=cliente.id
    )
    db.session.add(item)
    db.session.commit()
    
    flash(f'Item LPU "{nome}" adicionado ao cliente {cliente.nome}!', 'success')
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/config/delete/<string:tipo>/<int:id>', methods=['POST'])
@login_required
@admin_required
def deletar_config(tipo, id):
    """Remover serviço, LPU ou cliente"""
    if tipo == 'servico':
        item = TipoServico.query.get_or_404(id)
        nome = item.nome
        db.session.delete(item)
        flash(f'Serviço "{nome}" removido.', 'success')
    elif tipo == 'lpu':
        item = ItemLPU.query.get_or_404(id)
        nome = item.nome
        db.session.delete(item)
        flash(f'Item LPU "{nome}" removido.', 'success')
    elif tipo == 'cliente':
        item = Cliente.query.get_or_404(id)
        nome = item.nome
        db.session.delete(item)
        flash(f'Cliente "{nome}" e todos seus serviços/LPUs removidos.', 'success')
    else:
        flash('Tipo inválido.', 'danger')
        return redirect(url_for('admin.contratos'))
    
    db.session.commit()
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/config/update/<string:tipo>/<int:id>', methods=['POST'])
@login_required
@admin_required
def atualizar_config(tipo, id):
    """Atualizar valor ou nome de serviço/LPU via AJAX"""
    try:
        data = request.get_json()
        
        # Determine model
        if tipo == 'servico':
            item = TipoServico.query.get_or_404(id)
        elif tipo == 'lpu':
            item = ItemLPU.query.get_or_404(id)
        else:
            return jsonify({'error': 'Tipo inválido'}), 400
            
        # Update fields if present
        if 'nome' in data and data['nome'].strip():
            item.nome = data['nome'].strip()
            
        # Legacy
        if 'valor' in data:
            item.valor_receita = float(data['valor'])
            
        # New Fields
        numeric_fields = [
            'valor_receita', 'valor_custo_tecnico', 
            'valor_adicional_receita', 'valor_adicional_custo',
            'valor_hora_adicional_receita', 'valor_hora_adicional_custo'
        ]
        for field in numeric_fields:
            if field in data and hasattr(item, field):
                setattr(item, field, float(data[field]))
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# TABELA DE PRECOS POR CONTRATO (ContratoItem)
# =============================================================================

@admin_bp.route('/contrato/<int:id>/itens', methods=['GET'])
@login_required
@admin_required
def listar_contrato_itens(id):
    """Listar itens de preço personalizado de um contrato (API JSON)"""
    cliente = Cliente.query.get_or_404(id)

    itens = []
    for ci in cliente.itens.all():
        itens.append({
            'id': ci.id,
            'item_lpu_id': ci.item_lpu_id,
            'item_nome': ci.item_lpu.nome if ci.item_lpu else 'N/A',
            'valor_venda': float(ci.valor_venda or 0),
            'valor_repasse': float(ci.valor_repasse or 0) if ci.valor_repasse else None,
            'valor_custo': float(ci.item_lpu.valor_custo or 0) if ci.item_lpu else 0,
            'valor_catalogo': float(ci.item_lpu.valor_receita or 0) if ci.item_lpu else 0,
            'margem': ci.margem,
            'margem_percent': round(ci.margem_percent, 1)
        })

    return jsonify({
        'cliente_id': cliente.id,
        'cliente_nome': cliente.nome,
        'itens': itens
    })


@admin_bp.route('/contrato/<int:id>/itens', methods=['POST'])
@login_required
@admin_required
def adicionar_contrato_item(id):
    """Adicionar/atualizar item de preço personalizado a um contrato"""
    cliente = Cliente.query.get_or_404(id)

    # Pode vir de form ou JSON
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()

    item_lpu_id = data.get('item_lpu_id') or data.get('item_id')
    valor_venda = data.get('valor_venda')
    valor_repasse = data.get('valor_repasse')

    if not item_lpu_id or not valor_venda:
        if request.is_json:
            return jsonify({'error': 'item_lpu_id e valor_venda são obrigatórios'}), 400
        flash('Peça e valor de venda são obrigatórios.', 'danger')
        return redirect(url_for('admin.contratos'))

    try:
        item_lpu_id = int(item_lpu_id)
        valor_venda = float(valor_venda)
        valor_repasse = float(valor_repasse) if valor_repasse else None
    except (ValueError, TypeError):
        if request.is_json:
            return jsonify({'error': 'Valores inválidos'}), 400
        flash('Valores inválidos.', 'danger')
        return redirect(url_for('admin.contratos'))

    # Verificar se item existe
    item_lpu = ItemLPU.query.get(item_lpu_id)
    if not item_lpu:
        if request.is_json:
            return jsonify({'error': 'Item LPU não encontrado'}), 404
        flash('Item LPU não encontrado.', 'danger')
        return redirect(url_for('admin.contratos'))

    # Verificar se já existe (upsert)
    contrato_item = ContratoItem.query.filter_by(
        cliente_id=cliente.id,
        item_lpu_id=item_lpu_id
    ).first()

    if contrato_item:
        # Atualizar existente
        contrato_item.valor_venda = valor_venda
        contrato_item.valor_repasse = valor_repasse
        contrato_item.ativo = True
        msg = f'Preço de "{item_lpu.nome}" atualizado para R$ {valor_venda:.2f}'
    else:
        # Criar novo
        contrato_item = ContratoItem(
            cliente_id=cliente.id,
            item_lpu_id=item_lpu_id,
            valor_venda=valor_venda,
            valor_repasse=valor_repasse
        )
        db.session.add(contrato_item)
        msg = f'Preço personalizado de "{item_lpu.nome}" adicionado: R$ {valor_venda:.2f}'

    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'message': msg,
            'contrato_item': contrato_item.to_dict()
        })

    flash(msg, 'success')
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/contrato/<int:contrato_id>/itens/<int:item_id>', methods=['DELETE', 'POST'])
@login_required
@admin_required
def remover_contrato_item(contrato_id, item_id):
    """Remover item de preço personalizado de um contrato"""
    contrato_item = ContratoItem.query.filter_by(
        cliente_id=contrato_id,
        item_lpu_id=item_id
    ).first_or_404()

    nome = contrato_item.item_lpu.nome if contrato_item.item_lpu else 'Item'

    # Se for DELETE via fetch ou POST com _method=DELETE
    if request.method == 'DELETE' or request.form.get('_method') == 'DELETE':
        db.session.delete(contrato_item)
        db.session.commit()

        if request.is_json or request.method == 'DELETE':
            return jsonify({'success': True, 'message': f'Preço personalizado de "{nome}" removido'})

        flash(f'Preço personalizado de "{nome}" removido.', 'success')
        return redirect(url_for('admin.contratos'))

    # POST normal = exclusão
    db.session.delete(contrato_item)
    db.session.commit()
    flash(f'Preço personalizado de "{nome}" removido.', 'success')
    return redirect(url_for('admin.contratos'))


@admin_bp.route('/contrato/<int:id>/itens/<int:item_id>', methods=['PUT'])
@login_required
@admin_required
def atualizar_contrato_item(contrato_id, item_id):
    """Atualizar valor de um item de preço personalizado"""
    contrato_item = ContratoItem.query.filter_by(
        cliente_id=contrato_id,
        item_lpu_id=item_id
    ).first_or_404()

    data = request.get_json()

    if 'valor_venda' in data:
        contrato_item.valor_venda = float(data['valor_venda'])
    if 'valor_repasse' in data:
        contrato_item.valor_repasse = float(data['valor_repasse']) if data['valor_repasse'] else None
    if 'ativo' in data:
        contrato_item.ativo = bool(data['ativo'])

    db.session.commit()

    return jsonify({
        'success': True,
        'contrato_item': contrato_item.to_dict()
    })


@admin_bp.route('/pecas-disponiveis')
@login_required
@admin_required
def listar_pecas_disponiveis():
    """Lista todas as peças disponíveis para seleção (API JSON)"""
    # Buscar todas as peças únicas do sistema
    pecas = ItemLPU.query.order_by(ItemLPU.nome).all()

    # Remover duplicatas por nome
    seen = set()
    pecas_unicas = []
    for p in pecas:
        if p.nome not in seen:
            seen.add(p.nome)
            pecas_unicas.append({
                'id': p.id,
                'nome': p.nome,
                'valor_receita': float(p.valor_receita or 0),
                'valor_custo': float(p.valor_custo or 0)
            })

    return jsonify(pecas_unicas)
