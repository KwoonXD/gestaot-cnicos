import os
from src import create_app, db

def verify():
    os.environ['DATABASE_URL'] = 'sqlite:///verify_db.db'
    os.environ['TESTING'] = 'true'
    
    print("Creating app...")
    app = create_app()
    print("App created.")
    
    with app.app_context():
        print("Creating tables...")
        db.create_all()
        print("Tables created.")
        
        from src.models import Tecnico
        t = Tecnico(nome="Test", contato="1", cidade="A")
        db.session.add(t)
        db.session.commit()
        print("Test data committed.")

if __name__ == '__main__':
    try:
        verify()
    except Exception as e:
        import traceback
        traceback.print_exc()
