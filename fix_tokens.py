from src import create_app, db
from src.models import Tecnico
import uuid

app = create_app()

def fix_tokens():
    with app.app_context():
        # Encontra técnicos sem token
        tecnicos_sem_token = Tecnico.query.filter(
            (Tecnico.token_acesso == None) | (Tecnico.token_acesso == '')
        ).all()
        
        count = 0
        for t in tecnicos_sem_token:
            t.token_acesso = str(uuid.uuid4())
            count += 1
            print(f"Gerando token para: {t.nome}")
        
        if count > 0:
            db.session.commit()
            print(f"Sucesso! {count} tokens gerados.")
        else:
            print("Todos os técnicos já possuem token.")

if __name__ == "__main__":
    fix_tokens()
