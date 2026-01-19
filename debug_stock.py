
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

try:
    from src import create_app, db
    from src.models import Tecnico, ItemLPU, TecnicoStock, StockMovement, User
    from src.services.stock_service import StockService
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

def run_test():
    db_path = "debug_concurrency.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath(db_path)}'
    
    # 1. Setup
    print("Setting up DB...")
    with app.app_context():
        db.create_all()
        u = User(username='test_debug', password_hash='hash', role='Admin')
        t = Tecnico(nome="Tecnico Debug", data_inicio="2025-01-01", cidade="SP", estado="SP", contato="11")
        i = ItemLPU(nome="Peca Debug", valor_custo=10.00)
        db.session.add_all([u, t, i])
        db.session.commit()
        
        t_id_val = t.id
        i_id_val = i.id
        u_id_val = u.id

    print(f"Setup Complete. T={t_id_val}, I={i_id_val}")

    # 2. Race Condition - Creation
    def add_stock():
        # Create NEW app context per thread to simulate requests
        with app.app_context():
            try:
                StockService.transferir_sede_para_tecnico(
                    tecnico_id=t_id_val,
                    item_id=i_id_val,
                    quantidade=10,
                    user_id=u_id_val
                )
                return "ok"
            except Exception as e:
                return f"ERR: {e}"

    print("Running Concurrent Threads...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(add_stock) for _ in range(5)]
        results = [f.result() for f in futures]
    
    print("Results:", results)
    
    # 3. Validation
    with app.app_context():
        stock = TecnicoStock.query.filter_by(tecnico_id=t_id_val, item_lpu_id=i_id_val).first()
        print(f"Final Stock: {stock.quantidade if stock else 'None'}")
        
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except:
            pass

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        import traceback
        traceback.print_exc()
