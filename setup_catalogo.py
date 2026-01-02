"""
Script para criar/atualizar o Catálogo de Serviços padrão.
Migra de TipoServico para CatalogoServico com as novas regras de negócio.
"""
from src import create_app, db
from src.models import Cliente, CatalogoServico, ItemLPU
from sqlalchemy import text

app = create_app()

# Catálogo padrão para Americanas
CATALOGO_AMERICANAS = [
    {
        'nome': 'TI Padrão (1ª Visita)',
        'valor_receita': 120.00,
        'exige_peca': False,
        'paga_tecnico': True,
        'horas_franquia': 2
    },
    {
        'nome': 'Zebra (1ª Visita)',
        'valor_receita': 190.00,
        'exige_peca': False,
        'paga_tecnico': True,
        'horas_franquia': 2
    },
    {
        'nome': 'Retorno SPARE (Troca Peça)',
        'valor_receita': 0.00,
        'exige_peca': True,
        'paga_tecnico': True,
        'horas_franquia': 2
    },
    {
        'nome': 'Improdutivo/Falha',
        'valor_receita': 0.00,
        'exige_peca': False,
        'paga_tecnico': False,
        'horas_franquia': 0
    },
    {
        'nome': 'Instalação',
        'valor_receita': 150.00,
        'exige_peca': False,
        'paga_tecnico': True,
        'horas_franquia': 3
    },
    {
        'nome': 'Manutenção Preventiva',
        'valor_receita': 100.00,
        'exige_peca': False,
        'paga_tecnico': True,
        'horas_franquia': 2
    }
]

# Itens LPU Migrados (Ex-Hardcoded)
LPU_ITEMS = [
    {'nome': 'Scanner', 'valor': 180.0},
    {'nome': 'CPU gerencia', 'valor': 250.0},
    {'nome': 'Monitor', 'valor': 200.0},
    {'nome': 'Teclado pdv', 'valor': 250.0},
    {'nome': 'Impressora Fiscal', 'valor': 280.0},
    {'nome': 'Memoria ram', 'valor': 300.0},
    {'nome': 'SSD/HD', 'valor': 300.0},
    {'nome': 'Cabo Scanner Zebra', 'valor': 180.0},
    {'nome': 'Cabo USB p/ Impressora 2mt', 'valor': 38.70},
    {'nome': 'HDMI', 'valor': 43.86},
    {'nome': 'VGA', 'valor': 47.30},
    {'nome': 'Cabo de força tripolar', 'valor': 38.70},
    {'nome': 'Cabo de força bipolar', 'valor': 30.96},
    {'nome': 'Cabo de força p/ fonte ATX', 'valor': 38.70},
    {'nome': 'Cabo de força SATA', 'valor': 43.77},
    {'nome': 'Cabo SATA', 'valor': 27.43},
    {'nome': 'Patch cord 3mt', 'valor': 35.24},
    {'nome': 'Conector RJ 45', 'valor': 2.06},
    {'nome': 'Conector RJ11', 'valor': 2.06},
    {'nome': 'Fonte CPU Interna mini', 'valor': 300.00},
    {'nome': 'Fonte Externa', 'valor': 180.00},
    # Revenda / Peças Novas
    {'nome': 'Scanner BR520 (Novo)', 'valor': 289.00},
    {'nome': 'CPU gerencia (Novo)', 'valor': 1000.00},
    {'nome': 'CPU PDV (Novo)', 'valor': 1350.00},
    {'nome': 'Monitor (Novo)', 'valor': 500.00},
    {'nome': 'Teclado GERTEC 44 (Novo)', 'valor': 700.90},
    {'nome': 'Impressora Fiscal MP4200 HS (Novo)', 'valor': 515.00},
    {'nome': 'Placa mãe (Novo)', 'valor': 600.00},
    {'nome': 'Gaveta GD56 M (Novo)', 'valor': 289.00},
    {'nome': 'Cabeça impressão (Novo)', 'valor': 2300.00}
]

with app.app_context():
    conn = db.engine.connect()
    
    # 1. Criar tabela catalogo_servicos se não existir
    create_catalogo = """
    CREATE TABLE IF NOT EXISTS catalogo_servicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome VARCHAR(100) NOT NULL,
        valor_receita FLOAT DEFAULT 0.0,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        exige_peca BOOLEAN DEFAULT 0,
        paga_tecnico BOOLEAN DEFAULT 1,
        horas_franquia INTEGER DEFAULT 2,
        ativo BOOLEAN DEFAULT 1
    )
    """
    
    # 1.1 Criar tabela itens_lpu se não existir
    create_lpu = """
    CREATE TABLE IF NOT EXISTS itens_lpu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome VARCHAR(100) NOT NULL,
        valor_receita FLOAT DEFAULT 0.0,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id)
    )
    """
    
    try:
        conn.execute(text(create_catalogo))
        conn.execute(text(create_lpu))
        conn.commit()
        print("OK: Tabelas catalogo_servicos e itens_lpu verificadas")
    except Exception as e:
        print(f"Erro criação tabelas: {e}")
    
    # 2. Adicionar novas colunas ao chamados se não existirem
    chamados_columns = [
        'ALTER TABLE chamados ADD COLUMN catalogo_servico_id INTEGER',
        'ALTER TABLE chamados ADD COLUMN horas_trabalhadas FLOAT DEFAULT 2.0',
        'ALTER TABLE chamados ADD COLUMN valor_horas_extras DECIMAL(10,2) DEFAULT 0.00'
    ]
    
    for sql in chamados_columns:
        try:
            conn.execute(text(sql))
            conn.commit()
            col = sql.split('COLUMN')[1].split()[0]
            print(f"OK: Adicionada coluna {col}")
        except Exception as e:
            if 'duplicate' in str(e).lower():
                col = sql.split('COLUMN')[1].split()[0]
                print(f"SKIP: Coluna {col} já existe")
            else:
                print(f"Column: {e}")
    
    # 3. Adicionar valor_hora_adicional ao tecnicos
    try:
        conn.execute(text('ALTER TABLE tecnicos ADD COLUMN valor_hora_adicional DECIMAL(10,2) DEFAULT 30.00'))
        conn.commit()
        print("OK: Adicionada coluna valor_hora_adicional")
    except Exception as e:
        if 'duplicate' in str(e).lower():
            print("SKIP: Coluna valor_hora_adicional já existe")
        else:
            print(f"valor_hora_adicional: {e}")
    
    # 4. Buscar ou criar cliente Americanas
    americanas = Cliente.query.filter_by(nome='Americanas').first()
    if not americanas:
        americanas = Cliente(nome='Americanas', ativo=True)
        db.session.add(americanas)
        db.session.commit()
        print("OK: Cliente Americanas criado")
    else:
        print("OK: Cliente Americanas encontrado")
    
    # 5. Criar/Atualizar Catálogo
    for item in CATALOGO_AMERICANAS:
        existing = CatalogoServico.query.filter_by(
            nome=item['nome'],
            cliente_id=americanas.id
        ).first()
        
        if existing:
            # Atualizar
            existing.valor_receita = item['valor_receita']
            existing.exige_peca = item['exige_peca']
            existing.paga_tecnico = item['paga_tecnico']
            existing.horas_franquia = item['horas_franquia']
            print(f"UPDATE SERVICO: {item['nome']}")
        else:
            # Criar
            servico = CatalogoServico(
                nome=item['nome'],
                valor_receita=item['valor_receita'],
                cliente_id=americanas.id,
                exige_peca=item['exige_peca'],
                paga_tecnico=item['paga_tecnico'],
                horas_franquia=item['horas_franquia']
            )
            db.session.add(servico)
            print(f"CREATE SERVICO: {item['nome']}")
            
    # 6. Criar/Atualizar Itens LPU
    for item in LPU_ITEMS:
        existing = ItemLPU.query.filter_by(
            nome=item['nome'],
            cliente_id=americanas.id
        ).first()
        
        if existing:
            existing.valor_receita = item['valor']
            # print(f"UPDATE LPU: {item['nome']}")
        else:
            novo_lpu = ItemLPU(
                nome=item['nome'],
                valor_receita=item['valor'],
                cliente_id=americanas.id
            )
            db.session.add(novo_lpu)
            print(f"CREATE LPU: {item['nome']}")
    
    db.session.commit()
    print("\n✅ Configuração concluída com sucesso!")

