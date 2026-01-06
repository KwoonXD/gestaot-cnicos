from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from src.decorators import admin_required
from src.models import AuditLog, User, Cliente, TipoServico, ItemLPU, db
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
    return render_template('admin_contratos.html', clientes=clientes)


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
    valor = request.form.get('valor', 0)
    cobra_visita = request.form.get('cobra_visita', 'on') == 'on'
    
    if not nome:
        flash('Nome do serviço é obrigatório.', 'danger')
        return redirect(url_for('admin.contratos'))
    
    try:
        valor = float(valor)
    except:
        valor = 0.0
    
    servico = TipoServico(
        nome=nome,
        valor_receita=valor,
        cliente_id=cliente.id
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
        if 'valor' in data:
            item.valor_receita = float(data['valor'])
            
        if 'nome' in data:
            if not data['nome'].strip():
                return jsonify({'error': 'Nome não pode ser vazio'}), 400
            item.nome = data['nome'].strip()
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
