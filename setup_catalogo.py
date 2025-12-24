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
    try:
        conn.execute(text(create_catalogo))
        conn.commit()
        print("OK: Tabela catalogo_servicos criada/verificada")
    except Exception as e:
        print(f"Tabela catalogo_servicos: {e}")
    
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
            print(f"UPDATE: {item['nome']}")
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
            print(f"CREATE: {item['nome']}")
    
    db.session.commit()
    print("\n✅ Catálogo de Serviços configurado com sucesso!")
    
    # 6. Listar para conferência
    print("\n📋 Catálogo atual:")
    for s in CatalogoServico.query.filter_by(cliente_id=americanas.id).all():
        peca = "📦 Exige Peça" if s.exige_peca else ""
        paga = "💰 Paga Téc" if s.paga_tecnico else "⛔ Não paga"
        print(f"   - {s.nome}: R$ {s.valor_receita} | {peca} | {paga} | {s.horas_franquia}h franquia")
