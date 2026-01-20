"""Criar usuario admin no SQLite local."""
from src import create_app, db
from src.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Criar tabelas
    db.create_all()
    
    # Verificar se admin existe
    user = User.query.filter_by(username='admin').first()
    if user:
        user.password_hash = generate_password_hash('admin123')
        user.role = 'Admin'
        print("Usuario admin atualizado!")
    else:
        user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='Admin'
        )
        db.session.add(user)
        print("Usuario admin criado!")
    
    db.session.commit()
    
    # Verificar
    test = User.query.filter_by(username='admin').first()
    print(f"Verificacao: {test.username} - check_password: {test.check_password('admin123')}")
    print("\n" + "="*40)
    print("LOGIN: admin / admin123")
    print("="*40)
