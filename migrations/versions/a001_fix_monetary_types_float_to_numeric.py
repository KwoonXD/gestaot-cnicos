"""Fix monetary types: Float to Numeric(10,2)

Revision ID: a001
Revises: 2908569d81de
Create Date: 2026-01-14 10:00:00.000000

OBJETIVO
========
Converte colunas monetarias de Float para Numeric(10,2)
para garantir precisao em calculos financeiros.

TABELAS AFETADAS
================
- catalogo_servicos (6 colunas)
- itens_lpu (2 colunas)
- itens_lpu_preco_historico (4 colunas)
- contrato_itens (2 colunas)
- stock_movements (1 coluna)

PRE-REQUISITOS
==============
Executar relatorio de reconciliacao ANTES da migration:
    psql -f scripts/pre_migration_a001_report.sql

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a001'
down_revision = '2908569d81de'
branch_labels = None
depends_on = None


# Colunas a converter: (tabela, coluna, nullable)
COLUMNS_TO_CONVERT = [
    ('catalogo_servicos', 'valor_receita', True),
    ('catalogo_servicos', 'valor_custo_tecnico', True),
    ('catalogo_servicos', 'valor_adicional_receita', True),
    ('catalogo_servicos', 'valor_adicional_custo', True),
    ('catalogo_servicos', 'valor_hora_adicional_receita', True),
    ('catalogo_servicos', 'valor_hora_adicional_custo', True),
    ('itens_lpu', 'valor_receita', True),
    ('itens_lpu', 'valor_custo', True),
    ('itens_lpu_preco_historico', 'valor_custo_anterior', True),
    ('itens_lpu_preco_historico', 'valor_receita_anterior', True),
    ('itens_lpu_preco_historico', 'valor_custo_novo', True),
    ('itens_lpu_preco_historico', 'valor_receita_novo', True),
    ('contrato_itens', 'valor_venda', False),
    ('contrato_itens', 'valor_repasse', True),
    ('stock_movements', 'custo_unitario', True),
]


def table_exists(conn, table_name):
    """Verifica se tabela existe (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    
    if dialect == 'sqlite':
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
        ), {'t': table_name})
        return result.fetchone() is not None
    else:
        # PostgreSQL
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
            )
        """), {'t': table_name})
        return result.scalar()


def column_exists(conn, table_name, column_name):
    """Verifica se coluna existe (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns
    else:
        # PostgreSQL
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = :t AND column_name = :c
            )
        """), {'t': table_name, 'c': column_name})
        return result.scalar()


def get_column_type(conn, table_name, column_name):
    """Retorna o tipo atual da coluna (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        for row in result.fetchall():
            if row[1] == column_name:
                return row[2].lower()  # type is in position 2
        return None
    else:
        # PostgreSQL
        result = conn.execute(text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :t AND column_name = :c
        """), {'t': table_name, 'c': column_name})
        row = result.fetchone()
        return row[0] if row else None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a001] Conversao Float -> Numeric(10,2)")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # ==========================================================================
    # SQLite: SKIP - SQLite usa type affinity, nao tem tipos rigidos
    # ==========================================================================
    if dialect == 'sqlite':
        print("\n[INFO] SQLite detectado - conversion de tipos nao necessaria")
        print("[INFO] SQLite usa 'type affinity' - valores numericos sao tratados automaticamente")
        print("[OK] Migration a001 concluida (SQLite mode)")
        return

    # ==========================================================================
    # PostgreSQL: Proceeder com conversao
    # ==========================================================================

    # FASE 1: RELATORIO DE RECONCILIACAO PRE-MIGRACAO

    print("\n[FASE 1] Gerando relatorio de reconciliacao...")

    # Criar tabela de auditoria
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS _migration_a001_reconciliation (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100),
            column_name VARCHAR(100),
            record_count INTEGER,
            sum_before DOUBLE PRECISION,
            min_before DOUBLE PRECISION,
            max_before DOUBLE PRECISION,
            precision_loss_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    for table, column, nullable in COLUMNS_TO_CONVERT:
        if not table_exists(conn, table):
            print(f"  [SKIP] Tabela {table} nao existe")
            continue

        if not column_exists(conn, table, column):
            print(f"  [SKIP] Coluna {table}.{column} nao existe")
            continue

        current_type = get_column_type(conn, table, column)
        if current_type == 'numeric':
            print(f"  [SKIP] {table}.{column} ja e numeric")
            continue

        # Coletar metricas pre-conversao
        result = conn.execute(text(f"""
            SELECT
                COUNT(*) as cnt,
                COALESCE(SUM({column}), 0) as total,
                MIN({column}) as min_val,
                MAX({column}) as max_val,
                COUNT(*) FILTER (
                    WHERE {column} IS NOT NULL
                    AND {column} != ROUND({column}::numeric, 2)
                ) as precision_loss
            FROM {table}
        """))
        row = result.fetchone()
        cnt, total, min_val, max_val, precision_loss = row

        # Registrar metricas
        conn.execute(text("""
            INSERT INTO _migration_a001_reconciliation
            (table_name, column_name, record_count, sum_before, min_before, max_before, precision_loss_count)
            VALUES (:t, :c, :cnt, :total, :min, :max, :loss)
        """), {
            't': table, 'c': column, 'cnt': cnt,
            'total': total, 'min': min_val, 'max': max_val, 'loss': precision_loss
        })

        if precision_loss > 0:
            print(f"  [WARN] {table}.{column}: {precision_loss} valores perderao precisao (arredondamento)")
        else:
            print(f"  [OK] {table}.{column}: {cnt} registros, soma={total}")

    # ==========================================================================
    # FASE 2: CONVERSAO DE TIPOS
    # ==========================================================================

    print("\n[FASE 2] Convertendo tipos...")

    for table, column, nullable in COLUMNS_TO_CONVERT:
        if not table_exists(conn, table):
            continue

        if not column_exists(conn, table, column):
            continue

        current_type = get_column_type(conn, table, column)
        if current_type == 'numeric':
            continue

        print(f"  Convertendo {table}.{column}...")

        # PostgreSQL: ALTER COLUMN ... TYPE ... USING
        conn.execute(text(f"""
            ALTER TABLE {table}
            ALTER COLUMN {column}
            TYPE NUMERIC(10, 2)
            USING ROUND({column}::numeric, 2)
        """))

    # ==========================================================================
    # FASE 3: VERIFICACAO POS-CONVERSAO
    # ==========================================================================

    print("\n[FASE 3] Verificando conversao...")

    # Adicionar colunas de verificacao
    conn.execute(text("""
        ALTER TABLE _migration_a001_reconciliation
        ADD COLUMN IF NOT EXISTS sum_after DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP
    """))

    discrepancies = []

    for table, column, nullable in COLUMNS_TO_CONVERT:
        if not table_exists(conn, table):
            continue

        if not column_exists(conn, table, column):
            continue

        # Verificar soma pos-conversao
        result = conn.execute(text(f"""
            SELECT COALESCE(SUM({column}), 0) FROM {table}
        """))
        sum_after = result.scalar()

        # Atualizar registro
        conn.execute(text("""
            UPDATE _migration_a001_reconciliation
            SET sum_after = :sum_after, verified_at = CURRENT_TIMESTAMP
            WHERE table_name = :t AND column_name = :c
        """), {'sum_after': sum_after, 't': table, 'c': column})

        # Buscar soma anterior
        result = conn.execute(text("""
            SELECT sum_before FROM _migration_a001_reconciliation
            WHERE table_name = :t AND column_name = :c
        """), {'t': table, 'c': column})
        row = result.fetchone()
        sum_before = row[0] if row else 0

        # Verificar discrepancia significativa (> 0.01 por registro)
        if sum_before and abs(float(sum_after or 0) - float(sum_before)) > 0.01:
            diff = float(sum_after or 0) - float(sum_before)
            discrepancies.append(f"{table}.{column}: diff={diff:.4f}")

    if discrepancies:
        print("\n  [WARN] Discrepancias detectadas (esperado por arredondamento):")
        for d in discrepancies:
            print(f"    - {d}")
    else:
        print("  [OK] Nenhuma discrepancia significativa")

    print("\n" + "=" * 70)
    print("[MIGRATION a001] Conversao concluida com sucesso")
    print("Relatorio salvo em: _migration_a001_reconciliation")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()

    print("[MIGRATION a001 DOWNGRADE] Revertendo para Float...")
    print("[WARN] Esta operacao pode causar perda de precisao")

    for table, column, nullable in COLUMNS_TO_CONVERT:
        if not table_exists(conn, table):
            continue

        if not column_exists(conn, table, column):
            continue

        current_type = get_column_type(conn, table, column)
        if current_type != 'numeric':
            continue

        print(f"  Revertendo {table}.{column} para Float...")

        conn.execute(text(f"""
            ALTER TABLE {table}
            ALTER COLUMN {column}
            TYPE DOUBLE PRECISION
        """))

    print("[MIGRATION a001 DOWNGRADE] Concluido")
    print("[INFO] Tabela _migration_a001_reconciliation mantida para auditoria")
