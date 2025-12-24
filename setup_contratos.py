"""
Script to add new tables for the Contract Management Engine.
Run this once to create clientes, tipos_servico, and itens_lpu tables.
"""
from src import create_app, db
from src.models import Cliente, TipoServico, ItemLPU

app = create_app()

with app.app_context():
    # Create all tables (will skip existing ones)
    db.create_all()
    
    # Seed default data if clientes table is empty
    if Cliente.query.count() == 0:
        print("Seeding default contract data...")
        
        # Cliente: Americanas
        americanas = Cliente(nome='Americanas')
        db.session.add(americanas)
        db.session.flush()  # Get ID
        
        # Tipos de Serviço - Americanas
        db.session.add(TipoServico(nome='TI Geral', valor_receita=120.00, cliente_id=americanas.id))
        db.session.add(TipoServico(nome='Zebra', valor_receita=190.00, cliente_id=americanas.id))
        db.session.add(TipoServico(nome='Ida SPARE', valor_receita=120.00, cliente_id=americanas.id))
        db.session.add(TipoServico(nome='Retorno SPARE', valor_receita=0.00, cobra_visita=False, cliente_id=americanas.id))
        
        # LPU Items - Americanas
        lpu_items = [
            ("Scanner", 180.00),
            ("CPU gerencia", 200.00),
            ("Monitor", 150.00),
            ("Teclado pdv", 80.00),
            ("Impressora Fiscal", 250.00),
            ("Memoria ram", 60.00),
            ("SSD/HD", 100.00),
            ("Cabo Scanner Zebra", 35.00),
            ("Cabo USB p/ Impressora 2mt", 20.00),
            ("Fonte CPU Interna mini", 90.00),
            ("Fonte Externa", 70.00),
        ]
        for nome, valor in lpu_items:
            db.session.add(ItemLPU(nome=nome, valor_receita=valor, cliente_id=americanas.id))
        
        db.session.commit()
        print(f"  -> Created 'Americanas' with services and LPU items.")
    else:
        print("Clientes table already has data, skipping seed.")
    
    print("\nContract tables ready!")
