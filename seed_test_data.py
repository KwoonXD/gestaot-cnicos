from src import create_app
from src.models import db, Tecnico, ItemLPU, TecnicoStock
from datetime import date

app = create_app()

def seed_test_data():
    with app.app_context():
        print("Starting test data seeding...")

        # 1. Create Technician
        tecnico = Tecnico.query.filter_by(nome="Técnico Teste 01").first()
        if not tecnico:
            tecnico = Tecnico(
                nome="Técnico Teste 01",
                contato="(11) 99999-9999",
                cidade="São Paulo",
                estado="SP",
                status="Ativo",
                data_inicio=date.today(),
                valor_por_atendimento=120.00,
                valor_adicional_loja=20.00
            )
            db.session.add(tecnico)
            db.session.commit()
            print(f"Created Technician: {tecnico.nome}")
        else:
            print(f"Technician already exists: {tecnico.nome}")

        # 2. Create Catalog Item
        item = ItemLPU.query.filter_by(nome="Cabo UTP CAT6 (Teste)").first()
        if not item:
            item = ItemLPU(
                nome="Cabo UTP CAT6 (Teste)",
                valor_receita=0.0,
                cliente_id=None # Global item, per recent fix
            )
            db.session.add(item)
            db.session.commit()
            print(f"Created ItemLPU: {item.nome}")
        else:
            print(f"ItemLPU already exists: {item.nome}")

        # 3. Set Stock Balance
        # Check current stock
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico.id, item_lpu_id=item.id).first()
        if not stock:
            stock = TecnicoStock(
                tecnico_id=tecnico.id,
                item_lpu_id=item.id,
                quantidade=10
            )
            db.session.add(stock)
            print("Created new stock record with 10 units.")
        else:
            stock.quantidade = 10
            print("Updated existing stock record to 10 units.")
        
        db.session.commit()
        print("Seeding complete successfully!")

if __name__ == "__main__":
    seed_test_data()
