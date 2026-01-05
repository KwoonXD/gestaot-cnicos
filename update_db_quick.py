import os
import sys

# Ensure current directory is in python path
sys.path.append(os.getcwd())

from src import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    with db.engine.connect() as conn:
        print("Adding column paga_tecnico...")
        try:
            conn.execute(text("ALTER TABLE catalogo_servicos ADD COLUMN paga_tecnico BOOLEAN DEFAULT 1"))
        except Exception as e:
            print(f"Error adding paga_tecnico: {e} (Column might already exist)")
            
        print("Adding column pagamento_integral...")
        try:
            conn.execute(text("ALTER TABLE catalogo_servicos ADD COLUMN pagamento_integral BOOLEAN DEFAULT 0"))
        except Exception as e:
            print(f"Error adding pagamento_integral: {e} (Column might already exist)")
            
        conn.commit()
    print("Migration finished!")
