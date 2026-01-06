
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), 'instance', 'gestao.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Columns to add
    cols = [
        ('valor_custo_tecnico', 'FLOAT', '0.0'),
        ('valor_adicional_receita', 'FLOAT', '0.0'),
        ('valor_adicional_custo', 'FLOAT', '0.0')
    ]
    
    for col, type_, default_ in cols:
        try:
            print(f"Adding {col}...")
            cursor.execute(f"ALTER TABLE catalogo_servicos ADD COLUMN {col} {type_} DEFAULT {default_}")
            print("Success.")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e):
                print(f"Column {col} already exists.")
            else:
                print(f"Error adding {col}: {e}")
                
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
