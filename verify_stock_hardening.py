from src import create_app, db
from src.models import Tecnico, ItemLPU, Chamado, StockMovement, TecnicoStock
from src.services.stock_service import StockService
from datetime import date
from decimal import Decimal

app = create_app()

def verify():
    with app.app_context():
        db.create_all()
        # Setup Data
        print("Setting up data...")
        t = Tecnico.query.filter_by(nome="Tecnico Stock Test").first()
        if not t:
            t = Tecnico(nome="Tecnico Stock Test", contato="123", cidade="SP", estado="SP", data_inicio=date.today())
            db.session.add(t)
        
        i = ItemLPU.query.filter_by(nome="Item Stock Test").first()
        if not i:
            i = ItemLPU(nome="Item Stock Test", valor_custo=10.50, valor_receita=20.00)
            db.session.add(i)
            
        db.session.commit()
        
        # Clear previous stock for test
        TecnicoStock.query.filter_by(tecnico_id=t.id, item_lpu_id=i.id).delete()
        StockMovement.query.filter_by(item_lpu_id=i.id).delete()
        db.session.commit()

        print("1. Testing Creation (Transfer Sede -> Tecnico)")
        StockService.transferir_sede_para_tecnico(t.id, i.id, 10, 1, obs="Initial Transfer")
        db.session.commit()
        
        stock = TecnicoStock.query.filter_by(tecnico_id=t.id, item_lpu_id=i.id).first()
        assert stock is not None
        assert stock.quantidade == 10
        print("   -> Stock created successfully.")

        print("2. Testing Usage (Registrar Uso)")
        # Create dummy wrapper called 'chamado' implied by id
        chamado_id = 9999
        custo = StockService.registrar_uso_chamado(t.id, i.id, chamado_id, 1, quantidade=2)
        
        # Commit manually as service doesn't commit usage anymore (transaction managed by caller)
        db.session.commit()
        
        stock = TecnicoStock.query.filter_by(tecnico_id=t.id, item_lpu_id=i.id).first()
        assert stock.quantidade == 8
        assert custo == Decimal("21.00") # 2 * 10.50
        print(f"   -> Usage recorded. New Balance: {stock.quantidade}. Cost: {custo}")

        print("3. Verifying Audit Trail (StockMovement)")
        movs = StockMovement.query.filter_by(item_lpu_id=i.id).order_by(StockMovement.id).all()
        assert len(movs) == 2
        
        # Check Creation Move
        m1 = movs[0]
        assert m1.tipo_movimento == 'ENVIO'
        assert m1.quantidade == 10
        
        # Check Usage Move
        m2 = movs[1]
        assert m2.tipo_movimento == 'USO'
        assert m2.quantidade == 2
        assert m2.chamado_id == chamado_id
        assert m2.custo_unitario == Decimal("10.50")
        
        print("   -> Audit trail verified.")
        print("SUCCESS")

if __name__ == "__main__":
    import traceback
    try:
        verify()
    except Exception:
        with open('error.log', 'w') as f:
            f.write(traceback.format_exc())
        traceback.print_exc()
        exit(1)
