from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    try:
        conn.execute(text('ALTER TABLE pagamentos ADD COLUMN comprovante_path VARCHAR(255)'))
        conn.commit()
        print("✅ Column 'comprovante_path' added successfully.")
    except Exception as e:
        if 'duplicate column' in str(e).lower():
             print("ℹ️ Column already exists.")
        else:
             print(f"❌ Error adding column: {e}")
