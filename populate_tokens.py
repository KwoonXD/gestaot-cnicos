from src import create_app, db
from src.models import Tecnico
import uuid

app = create_app()

with app.app_context():
    tecnicos = Tecnico.query.filter_by(token_acesso=None).all()
    count = 0
    for t in tecnicos:
        t.token_acesso = str(uuid.uuid4())
        count += 1
    
    if count > 0:
        db.session.commit()
        print(f"Tokens generated for {count} technicians.")
    else:
        print("All technicians already have tokens.")
