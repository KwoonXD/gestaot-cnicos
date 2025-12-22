import shutil
import os
import datetime
import logging
from dotenv import load_dotenv

# Setup Logging for Backup
logging.basicConfig(
    filename='logs/backup.log', 
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)

def backup_database():
    load_dotenv()
    
    # Get DB path from env or default
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or 'sqlite:///' not in db_url:
        logging.error("Database is not SQLite or DATABASE_URL not found.")
        print("Erro: Apenas SQLite é suportado por este script simples.")
        return

    # Extract path from sqlite:///instance/gestao.db or similar
    # Handling relative paths commonly used in Flask-SQLAlchemy
    db_path = db_url.replace('sqlite:///', '')
    
    # If using instance folder logic (common in Flask 2.x+), verify path
    if not os.path.exists(db_path):
        # Try finding it in root if not found (sometimes encoded differently)
        if os.path.exists('instance/' + db_path):
            db_path = 'instance/' + db_path
        elif os.path.exists(db_path.lstrip('/')):
             db_path = db_path.lstrip('/')
        else:
            logging.error(f"Database file not found at: {db_path}")
            print(f"Erro: Arquivo do banco não encontrado em {db_path}")
            return

    # Create backups folder
    backup_dir = 'backups'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # Generate filename
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_name = f"gestao_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_name)

    try:
        shutil.copy2(db_path, backup_path)
        logging.info(f"Backup successfully created at {backup_path}")
        print(f"Backup realizado com sucesso: {backup_path}")
    except Exception as e:
        logging.error(f"Failed to copy database: {str(e)}")
        print(f"Erro ao criar backup: {str(e)}")

if __name__ == "__main__":
    # Ensure logs folder exists
    if not os.path.exists('logs'):
        os.mkdir('logs')
        
    print("Iniciando backup...")
    backup_database()
