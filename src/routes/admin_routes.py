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
