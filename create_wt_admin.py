from app import app
from src import db
from src.models import User
from werkzeug.security import generate_password_hash

def create_admin():
    with app.app_context():
        # Check if user exists
        user = User.query.filter_by(username='WT').first()
        if user:
            print("User WT already exists. Updating password and role...")
            user.set_password('WT@2025R2N0V4')
            user.role = 'Admin'
        else:
            print("Creating User WT...")
            user = User(username='WT', role='Admin')
            user.set_password('WT@2025R2N0V4')
            db.session.add(user)
        
        db.session.commit()
        print("User WT configured successfully as Admin.")

if __name__ == '__main__':
    create_admin()
