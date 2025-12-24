from src import create_app, db
from sqlalchemy import text, inspect

app = create_app()

def update_schema():
    with app.app_context():
        inspector = inspect(db.engine)
        
        # 1. Update Tecnicos
        columns = [c['name'] for c in inspector.get_columns('tecnicos')]
        
        if 'valor_adicional_loja' not in columns:
            print("Adicionando valor_adicional_loja a tecnicos...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE tecnicos ADD COLUMN valor_adicional_loja NUMERIC(10, 2) DEFAULT 20.00"))
                conn.commit()
        
        # 2. Update Chamados
        columns = [c['name'] for c in inspector.get_columns('chamados')]
        
        new_cols = [
            ('loja', 'VARCHAR(100)'),
            ('tipo_resolucao', "VARCHAR(50) DEFAULT 'Resolvido'"),
            ('valor_receita_servico', 'NUMERIC(10, 2) DEFAULT 0.00'),
            ('peca_usada', 'VARCHAR(100)'),
            ('valor_receita_peca', 'NUMERIC(10, 2) DEFAULT 0.00'),
            ('custo_peca', 'NUMERIC(10, 2) DEFAULT 0.00'),
            ('fornecedor_peca', "VARCHAR(20) DEFAULT 'Empresa'"),
            ('custo_atribuido', 'NUMERIC(10, 2) DEFAULT 0.00')
        ]
        
        with db.engine.connect() as conn:
            for col_name, col_type in new_cols:
                if col_name not in columns:
                    print(f"Adicionando {col_name} a chamados...")
                    conn.execute(text(f"ALTER TABLE chamados ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            
        print("Schema atualizado com sucesso!")

if __name__ == "__main__":
    update_schema()
