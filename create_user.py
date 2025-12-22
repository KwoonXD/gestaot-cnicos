from app import app, db
from models import User

def create_admin():
    with app.app_context():
        # Check if admin exists
        if User.query.filter_by(username='admin').first():
            print("Admin user already exists.")
            return

        # Create admin
        user = User(username='admin')
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()
        print("Admin user created successfully! (User: admin / Pass: admin123)")

if __name__ == '__main__':
    create_admin()
