"""
Script para adicionar colunas hora_inicio e hora_fim ao chamados.
"""
from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    
    # Adicionar novas colunas
    columns = [
        'ALTER TABLE chamados ADD COLUMN hora_inicio VARCHAR(5)',
        'ALTER TABLE chamados ADD COLUMN hora_fim VARCHAR(5)'
    ]
    
    for sql in columns:
        try:
            conn.execute(text(sql))
            conn.commit()
            col = sql.split('COLUMN')[1].split()[0]
            print(f"OK: Adicionada coluna {col}")
        except Exception as e:
            if 'duplicate' in str(e).lower():
                col = sql.split('COLUMN')[1].split()[0]
                print(f"SKIP: Coluna {col} já existe")
            else:
                print(f"Erro: {e}")
    
    print("\n✅ Schema atualizado!")
