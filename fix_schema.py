"""
Script to add missing columns to the chamados table.
Run this once to fix the database schema after model changes.
"""
from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    
    # Add missing columns one by one, ignoring errors if they already exist
    columns_to_add = [
        'ALTER TABLE chamados ADD COLUMN cidade VARCHAR(100) DEFAULT "Indefinido"',
        'ALTER TABLE chamados ADD COLUMN is_adicional BOOLEAN DEFAULT 0',
        'ALTER TABLE chamados ADD COLUMN valor_receita_total NUMERIC(10,2) DEFAULT 0'
    ]
    
    for sql in columns_to_add:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"OK: {sql.split('ADD COLUMN')[1].split()[0]}")
        except Exception as e:
            if 'duplicate column name' in str(e).lower():
                print(f"SKIP (already exists): {sql.split('ADD COLUMN')[1].split()[0]}")
            else:
                print(f"ERROR: {e}")
    
    print("\nSchema update complete. Please restart the Flask app.")
