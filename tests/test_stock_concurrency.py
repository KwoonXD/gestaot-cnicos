
import pytest
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
from src import create_app, db
from src.models import Tecnico, ItemLPU, TecnicoStock, StockMovement, User
from src.services.stock_service import StockService
from decimal import Decimal

@pytest.fixture
def app():
    import os
    db_path = "test_concurrency.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    app = create_app()
    app.config['TESTING'] = True
    # File DB allows multi-thread access (with proper locking) unlike default :memory:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath(db_path)}'
    
    with app.app_context():
        db.create_all()
        # Seed required data
        u = User(username='test_stock', password_hash='hash', role='Admin')
        t = Tecnico(nome="Tecnico Teste", data_inicio="2025-01-01", cidade="SP", estado="SP", contato="1199999999")
        i = ItemLPU(nome="Peca Teste", valor_custo=10.00)
        db.session.add_all([u, t, i])
        db.session.commit()
        
        yield app
        db.session.remove()
        db.drop_all()
    
    if os.path.exists(db_path):
        os.remove(db_path)

def test_stock_creation_race_condition(app):
    """
    Test race condition during initial stock creation.
    Multiple threads trying to add stock for the same (tecnico, item) simultaneously.
    Should handle IntegrityError and succeed eventually.
    """
    with app.app_context():
        tecnico = Tecnico.query.first()
        item = ItemLPU.query.first()
        user = User.query.first()
        t_id = tecnico.id
        i_id = item.id
        u_id = user.id

    def add_stock():
        with app.app_context():
            # Simulated concurrent add
            try:
                StockService.transferir_sede_para_tecnico(
                    tecnico_id=t_id,
                    item_id=i_id,
                    quantidade=10,
                    user_id=u_id
                )
                return "success"
            except Exception as e:
                return str(e)

    # Launch 5 concurrent threads
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(add_stock) for _ in range(5)]
        results = [f.result() for f in futures]

    # Verify results
    with app.app_context():
        stock = TecnicoStock.query.filter_by(tecnico_id=t_id, item_lpu_id=i_id).first()
        movements = StockMovement.query.filter_by(destino_tecnico_id=t_id).count()
        
        # All 5 should succeed (add 10 each -> 50 total)
        # Assuming the service handles the race correctly
        assert stock is not None
        assert stock.quantidade == 50
        assert movements == 5 

def test_stock_usage_concurrency(app):
    """
    Test race condition during stock usage (decrement).
    Threads trying to consume stock simultaneously.
    Should prevent negative balance if logic is correct (though our logic currently allows negative per requirements, 
    key is row locking to prevent lost updates).
    """
    with app.app_context():
        tecnico = Tecnico.query.first()
        item = ItemLPU.query.first()
        user = User.query.first()
        
        # Setup initial stock: 100
        StockService.transferir_sede_para_tecnico(tecnico.id, item.id, 100, user.id)
        
        t_id = tecnico.id
        i_id = item.id
        u_id = user.id

    def consume_stock():
        with app.app_context():
            try:
                # Use devolver_tecnico_para_sede for atomic decrement (1 unit)
                StockService.devolver_tecnico_para_sede(
                    tecnico_id=t_id,
                    item_id=i_id,
                    qtd=1,
                    user_id=u_id,
                    obs="Simulated Usage"
                )
                return True
            except Exception:
                return False

    # Launch 50 concurrent threads consuming 1 item each
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(consume_stock) for _ in range(50)]
        results = [f.result() for f in futures]

    with app.app_context():
        stock = TecnicoStock.query.filter_by(tecnico_id=t_id, item_lpu_id=i_id).first()
        # Initial 100 - 50 used = 50 remaining
        assert stock.quantidade == 50

