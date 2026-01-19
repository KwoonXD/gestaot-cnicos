"""Deprecate Chamado.valor - Phase 1: Backfill and documentation

Revision ID: a003
Revises: a002
Create Date: 2026-01-14 10:02:00.000000

PLANO DE DEPRECACAO (3 FASES)
=============================

FASE 1 (ESTA MIGRATION):
- Backfill: copiar valor -> custo_atribuido onde custo_atribuido = 0
- Documentar deprecacao via COMMENT ON COLUMN
- Gerar relatorio de uso do campo
- NAO altera DDL (campo permanece NOT NULL)

FASE 2 (30 dias depois):
- Verificar que nenhum codigo usa o campo diretamente
- Remover campo do to_dict() e APIs
- Tornar campo nullable

FASE 3 (60 dias depois):
- DROP COLUMN valor

MOTIVO DA DEPRECACAO
====================
- Campo duplica informacao de custo_atribuido
- Semantica confusa (era "valor pago ao tecnico")
- Novo modelo usa custo_atribuido para custos

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a003'
down_revision = 'a002'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Verifica se tabela existe (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
        ), {'t': table_name})
        return result.fetchone() is not None
    else:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
            )
        """), {'t': table_name})
        return result.scalar()


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a003] Deprecacao de chamados.valor - Fase 1")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # SQLite: Skip COMMENT e operações PostgreSQL-específicas
    if dialect == 'sqlite':
        print("\\n[INFO] SQLite detectado - aplicando apenas backfill")
        if table_exists(conn, 'chamados'):
            # Apenas backfill simples
            result = conn.execute(text("""
                UPDATE chamados
                SET custo_atribuido = valor
                WHERE valor IS NOT NULL
                AND valor > 0
                AND (custo_atribuido IS NULL OR custo_atribuido = 0)
            """))
            print(f"  [OK] Backfill aplicado")
        print("[OK] Migration a003 concluida (SQLite mode)")
        return

    if not table_exists(conn, 'chamados'):
        print("[SKIP] Tabela chamados nao existe")
        return

    # ==========================================================================
    # FASE 1.1: DIAGNOSTICO
    # ==========================================================================

    print("\n[FASE 1.1] Diagnostico de uso do campo...")

    # Criar tabela de auditoria
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS _migration_a003_deprecation_log (
            id SERIAL PRIMARY KEY,
            metric_name VARCHAR(100),
            metric_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Estatisticas gerais
    result = conn.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE valor IS NOT NULL AND valor > 0) as com_valor,
            COUNT(*) FILTER (WHERE custo_atribuido IS NOT NULL AND custo_atribuido > 0) as com_custo_atribuido,
            COUNT(*) FILTER (
                WHERE valor IS NOT NULL AND valor > 0
                AND (custo_atribuido IS NULL OR custo_atribuido = 0)
            ) as valor_sem_custo,
            COUNT(*) FILTER (
                WHERE valor IS NOT NULL AND valor > 0
                AND custo_atribuido IS NOT NULL AND custo_atribuido > 0
                AND valor != custo_atribuido
            ) as valor_diferente_custo
        FROM chamados
    """))
    row = result.fetchone()
    total, com_valor, com_custo, valor_sem_custo, valor_diff = row

    print(f"  Total de chamados: {total}")
    print(f"  Com valor > 0: {com_valor}")
    print(f"  Com custo_atribuido > 0: {com_custo}")
    print(f"  Valor preenchido mas custo_atribuido vazio: {valor_sem_custo}")
    print(f"  Valor diferente de custo_atribuido: {valor_diff}")

    # Registrar metricas
    metrics = [
        ('total_chamados', str(total)),
        ('chamados_com_valor', str(com_valor)),
        ('chamados_com_custo_atribuido', str(com_custo)),
        ('backfill_necessario', str(valor_sem_custo)),
        ('valores_divergentes', str(valor_diff)),
    ]

    for name, value in metrics:
        conn.execute(text("""
            INSERT INTO _migration_a003_deprecation_log (metric_name, metric_value)
            VALUES (:name, :value)
        """), {'name': name, 'value': value})

    # ==========================================================================
    # FASE 1.2: BACKFILL
    # ==========================================================================

    if valor_sem_custo > 0:
        print(f"\n[FASE 1.2] Backfill de {valor_sem_custo} registros...")

        # Criar log detalhado do backfill
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migration_a003_backfill_detail (
                chamado_id INTEGER PRIMARY KEY,
                valor_original NUMERIC(10,2),
                custo_atribuido_original NUMERIC(10,2),
                backfilled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Registrar antes de modificar
        conn.execute(text("""
            INSERT INTO _migration_a003_backfill_detail (chamado_id, valor_original, custo_atribuido_original)
            SELECT id, valor, custo_atribuido
            FROM chamados
            WHERE valor IS NOT NULL AND valor > 0
            AND (custo_atribuido IS NULL OR custo_atribuido = 0)
        """))

        # Executar backfill
        result = conn.execute(text("""
            UPDATE chamados
            SET custo_atribuido = valor
            WHERE valor IS NOT NULL AND valor > 0
            AND (custo_atribuido IS NULL OR custo_atribuido = 0)
            RETURNING id
        """))
        backfilled = result.fetchall()

        print(f"  [OK] {len(backfilled)} registros atualizados")

        conn.execute(text("""
            INSERT INTO _migration_a003_deprecation_log (metric_name, metric_value)
            VALUES ('backfill_executed', :cnt)
        """), {'cnt': str(len(backfilled))})
    else:
        print("\n[FASE 1.2] Backfill nao necessario")

    # ==========================================================================
    # FASE 1.3: DOCUMENTAR DEPRECACAO
    # ==========================================================================

    print("\n[FASE 1.3] Documentando deprecacao...")

    # Adicionar comentario na coluna (PostgreSQL)
    try:
        conn.execute(text("""
            COMMENT ON COLUMN chamados.valor IS
            'DEPRECATED (2026-01-14): Use custo_atribuido. Campo sera removido em 2026-03-14.
             Fase 1: Backfill executado
             Fase 2 (2026-02-14): Remover de APIs
             Fase 3 (2026-03-14): DROP COLUMN';
        """))
        print("  [OK] Comentario de deprecacao adicionado")
    except Exception as e:
        print(f"  [WARN] Nao foi possivel adicionar comentario: {e}")

    # Registrar data de deprecacao
    conn.execute(text("""
        INSERT INTO _migration_a003_deprecation_log (metric_name, metric_value)
        VALUES
            ('deprecation_date', '2026-01-14'),
            ('phase2_date', '2026-02-14'),
            ('removal_date', '2026-03-14'),
            ('replacement_field', 'custo_atribuido')
    """))

    # ==========================================================================
    # FASE 1.4: RELATORIO DE VALORES DIVERGENTES
    # ==========================================================================

    if valor_diff > 0:
        print(f"\n[FASE 1.4] Relatorio de {valor_diff} valores divergentes...")

        # Criar tabela de divergencias para analise
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migration_a003_divergences (
                chamado_id INTEGER PRIMARY KEY,
                valor NUMERIC(10,2),
                custo_atribuido NUMERIC(10,2),
                diferenca NUMERIC(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            INSERT INTO _migration_a003_divergences (chamado_id, valor, custo_atribuido, diferenca)
            SELECT id, valor, custo_atribuido, (valor - custo_atribuido) as diferenca
            FROM chamados
            WHERE valor IS NOT NULL AND valor > 0
            AND custo_atribuido IS NOT NULL AND custo_atribuido > 0
            AND valor != custo_atribuido
        """))

        # Mostrar amostra
        result = conn.execute(text("""
            SELECT chamado_id, valor, custo_atribuido, diferenca
            FROM _migration_a003_divergences
            ORDER BY ABS(diferenca) DESC
            LIMIT 5
        """))
        samples = result.fetchall()

        print("  Amostra das maiores divergencias:")
        for chamado_id, valor, custo, diff in samples:
            print(f"    - Chamado {chamado_id}: valor={valor}, custo={custo}, diff={diff}")

        print(f"\n  [WARN] Revisar _migration_a003_divergences para decidir qual valor manter")
    else:
        print("\n[FASE 1.4] Sem divergencias para reportar")

    print("\n" + "=" * 70)
    print("[MIGRATION a003] Fase 1 concluida")
    print("")
    print("PROXIMOS PASSOS:")
    print("  1. Verificar que APIs usam custo_atribuido em vez de valor")
    print("  2. Atualizar to_dict() para nao expor campo valor")
    print("  3. Apos 30 dias, aplicar Fase 2 (tornar nullable)")
    print("")
    print("TABELAS DE AUDITORIA:")
    print("  - _migration_a003_deprecation_log")
    print("  - _migration_a003_backfill_detail")
    print("  - _migration_a003_divergences")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()

    print("[MIGRATION a003 DOWNGRADE] Revertendo documentacao de deprecacao...")

    if table_exists(conn, 'chamados'):
        # Remover comentario
        try:
            conn.execute(text("""
                COMMENT ON COLUMN chamados.valor IS NULL;
            """))
            print("  [OK] Comentario de deprecacao removido")
        except Exception:
            pass

    # NAO reverte o backfill - custo_atribuido e o campo correto a usar

    print("[MIGRATION a003 DOWNGRADE] Concluido")
    print("[INFO] Backfill NAO revertido - custo_atribuido e o campo correto")
    print("[INFO] Tabelas de auditoria mantidas para referencia")
