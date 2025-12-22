from src import create_app, db
from flask_migrate import upgrade, migrate, init
import os

app = create_app()

with app.app_context():
    # Option 1: Try to create all tables (safest for dev if migrations are messy)
    try:
        print("Tentando criar tabelas...")
        db.create_all()
        print("Tabelas criadas com sucesso (db.create_all).")
    except Exception as e:
        print(f"Erro ao criar tabelas: {e}")

    # Option 2: Run migration if needed (optional, depends on if user prefers migration flow)
    # Since 'migrations' folder exists, we might want to respect it.
    # But often in dev, db.create_all() is enough for new tables if migrations aren't strictly guarded.
    # Let's just rely on create_all for the new models.
