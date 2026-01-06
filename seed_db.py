from src import create_app
from src.models import db, Cliente, CatalogoServico, ItemLPU, Tecnico

app = create_app()

with app.app_context():
    print("🔧 Criando Tabelas no Banco de Dados...")
    db.create_all()  # <--- A CORREÇÃO MÁGICA ESTÁ AQUI
    print("✅ Tabelas criadas com sucesso.")

    print("🌱 Semeando Dados...")

    # 1. Criar Cliente Padrão
    cliente = Cliente.query.filter_by(nome="Cliente Padrão").first()
    if not cliente:
        cliente = Cliente(nome="Cliente Padrão", ativo=True)
        db.session.add(cliente)
        db.session.commit() # Commit parcial para garantir que o ID exista
        print("✅ Cliente criado.")

    # 2. Criar Serviços
    servicos = ["Visita Técnica", "Instalação Fibra", "Manutenção Modem"]
    for nome in servicos:
        if not CatalogoServico.query.filter_by(nome=nome, cliente_id=cliente.id).first():
            s = CatalogoServico(nome=nome, cliente_id=cliente.id, valor_receita=150.0)
            db.session.add(s)
    print("✅ Serviços criados.")

    # 3. Criar Itens (Peças)
    # 3a. Itens do Cliente
    pecas_cliente = ["Modem WiFi 6", "Decodificador 4K"]
    for nome in pecas_cliente:
        if not ItemLPU.query.filter_by(nome=nome, cliente_id=cliente.id).first():
            # Importante: Item vinculado ao cliente
            i = ItemLPU(nome=nome, cliente_id=cliente.id, valor_receita=200.0)
            db.session.add(i)

    # 3b. Itens Gerais (Almoxarifado)
    pecas_geral = ["Conector RJ45", "Cabo UTP (Metro)", "Fita Isolante"]
    for nome in pecas_geral:
        # AQUI é onde dava o erro antes. Agora com nullable=True no model, vai passar.
        if not ItemLPU.query.filter_by(nome=nome, cliente_id=None).first():
            i = ItemLPU(nome=nome, cliente_id=None, valor_receita=0.0)
            db.session.add(i)
    
    print("✅ Itens/Peças criados.")

    db.session.commit()
    print("🚀 SUCESSO TOTAL! O Banco foi recriado e populado.")
