from src import create_app
from src.models import db, User

app = create_app()

def create_user(username, password, role='Admin'):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"Usuário '{username}' já existe. Atualizando senha e privilégios...")
            user.set_password(password)
            user.role = role
        else:
            print(f"Criando usuário '{username}' com role '{role}'...")
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
        
        db.session.commit()
        print(f"Sucesso! Usuário '{username}' configurado.")

if __name__ == '__main__':
    create_user('teste', 'teste123', 'Admin')
