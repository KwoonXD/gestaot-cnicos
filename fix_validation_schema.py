"""
Script to add validation and batch columns to the chamados table.
Run this once to fix the database schema after model changes.
"""
from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    
    columns_to_add = [
        'ALTER TABLE chamados ADD COLUMN batch_id VARCHAR(36)',
        'ALTER TABLE chamados ADD COLUMN status_validacao VARCHAR(20) DEFAULT "Pendente"',
        'ALTER TABLE chamados ADD COLUMN data_validacao DATETIME',
        'ALTER TABLE chamados ADD COLUMN validado_por_id INTEGER REFERENCES users(id)'
    ]
    
    for sql in columns_to_add:
        try:
            conn.execute(text(sql))
            conn.commit()
            col_name = sql.split('ADD COLUMN')[1].split()[0]
            print(f"OK: {col_name}")
        except Exception as e:
            if 'duplicate column name' in str(e).lower():
                col_name = sql.split('ADD COLUMN')[1].split()[0]
                print(f"SKIP (already exists): {col_name}")
            else:
                print(f"ERROR: {e}")
    
    # Create index on batch_id
    try:
        conn.execute(text('CREATE INDEX ix_chamados_batch_id ON chamados(batch_id)'))
        conn.commit()
        print("OK: Created index on batch_id")
    except Exception as e:
        if 'already exists' in str(e).lower():
            print("SKIP: Index already exists")
        else:
            print(f"Index creation skipped: {e}")
    
    print("\nSchema update complete!")
