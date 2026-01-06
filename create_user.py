from src import create_app
from src.models import db, User

app = create_app()

with app.app_context():
    # Check if admin exists
    user = User.query.filter_by(username='admin').first()
    if user:
        print("Usuário 'admin' já existe. Atualizando senha...")
        user.set_password('admin123')
    else:
        print("Criando usuário 'admin'...")
        user = User(username='admin')
        user.set_password('admin123')
        db.session.add(user)
    
    db.session.commit()
    print("Sucesso! Use:")
    print("Usuário: admin")
    print("Senha: admin123")
