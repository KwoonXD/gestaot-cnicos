from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verifica se o usuário tem a role correta
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Financeiro']:
            flash('Acesso negado. Você não tem permissão para acessar esta área.', 'danger')
            # Fallback seguro: se não tiver permissão, manda pro dashboard ou login
            # Ajuste 'operacional.dashboard' conforme sua rota real de dashboard
            return redirect(url_for('operacional.dashboard'))
        return f(*args, **kwargs)
    return decorated_function
