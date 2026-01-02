from app import create_app
from sqlalchemy import text
from src.models import db, TecnicoStock, StockMovement

def update_database():
    app = create_app()
    with app.app_context():
        print("Iniciando atualização do banco de dados...")
        
        # 1. Adicionar coluna saldo_atual em tecnicos
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE tecnicos ADD COLUMN saldo_atual FLOAT DEFAULT 0.0"))
                print("Coluna 'saldo_atual' adicionada em 'tecnicos'.")
        except Exception as e:
            if "duplicate column" in str(e) or "no such column" not in str(e): 
                # SQLite sometimes gives generic errors or specific ones. 
                # If column exists, it fails. We treat this as "already done".
                print(f"Nota: Coluna 'saldo_atual' provavelmente já existe ou erro ignorável: {e}")
            else:
                 print(f"Erro ao adicionar 'saldo_atual': {e}")

        # 2. Adicionar coluna chamado_id em lancamentos
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE lancamentos ADD COLUMN chamado_id INTEGER REFERENCES chamados(id)"))
                print("Coluna 'chamado_id' adicionada em 'lancamentos'.")
        except Exception as e:
             print(f"Nota: Coluna 'chamado_id' provavelmente já existe ou erro ignorável: {e}")

        # 3. Criar novas tabelas (TecnicoStock, StockMovement)
        # db.create_all() creates tables that don't exist.
        db.create_all()
        print("Tabelas novas (se houver) criadas via db.create_all().")
        
        print("Atualização concluída.")

if __name__ == "__main__":
    update_database()
