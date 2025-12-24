from flask import Blueprint, render_template, request, current_app
from flask_login import login_required
from src.decorators import admin_required
from src.models import AuditLog, User
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
