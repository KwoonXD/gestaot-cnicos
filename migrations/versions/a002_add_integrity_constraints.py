"""Add integrity constraints with data sanitization

Revision ID: a002
Revises: a001
Create Date: 2026-01-14 10:01:00.000000

OBJETIVO
========
Adiciona constraints de integridade ao banco de dados.
Inclui etapa de diagnostico e saneamento de dados antes de aplicar.

CONSTRAINTS ADICIONADOS
=======================
1. tecnico_stock: UNIQUE(tecnico_id, item_lpu_id)
2. stock_movements: CHECK(quantidade > 0)
3. stock_movements: CHECK(tipo_movimento IN (...))
4. solicitacoes_reposicao: CHECK(status IN (...))
5. chamados: CHECK(status_chamado IN (...))
6. chamados: CHECK(status_validacao IN (...))

VALORES PERMITIDOS
==================
- tipo_movimento: ENVIO, USO, DEVOLUCAO, AJUSTE, CORRECAO
- status (solicitacao): Pendente, Aprovada, Enviada, Recusada, Cancelada
- status_chamado: Finalizado, Concluido, Cancelado, Pendente, SPARE, Em Andamento
- status_validacao: Pendente, Aprovado, Rejeitado

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a002'
down_revision = 'a001'
branch_labels = None
depends_on = None


# Valores permitidos
TIPO_MOVIMENTO_VALIDOS = ['ENVIO', 'USO', 'DEVOLUCAO', 'AJUSTE', 'CORRECAO']
STATUS_SOLICITACAO_VALIDOS = ['Pendente', 'Aprovada', 'Enviada', 'Recusada', 'Cancelada']
STATUS_CHAMADO_VALIDOS = ['Finalizado', 'Concluído', 'Cancelado', 'Pendente', 'SPARE', 'Em Andamento']
STATUS_VALIDACAO_VALIDOS = ['Pendente', 'Aprovado', 'Rejeitado']


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


def constraint_exists(conn, constraint_name):
    """Verifica se constraint existe (SQLite retorna False)."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        # SQLite não tem sistema de constraints nomeados consultável facilmente
        return False
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = :c
        )
    """), {'c': constraint_name})
    return result.scalar()


def build_not_in_clause(values):
    """Builds a SQL NOT IN clause from a list of values.
    Safe because values are hardcoded constants, not user input.
    """
    quoted = ", ".join([f"'{v}'" for v in values])
    return f"NOT IN ({quoted})"


def _sanitize_data_sqlite(conn):
    """Saneamento de dados para SQLite (sem constraints, apenas dados)."""
    print("\\n[SQLite] Saneando dados para consistencia...")
    
    # Corrigir quantidade invalida em stock_movements
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_movements'"
    ))
    if result.fetchone():
        conn.execute(text("""
            UPDATE stock_movements SET quantidade = 1
            WHERE quantidade IS NULL OR quantidade <= 0
        """))
        print("  [OK] stock_movements.quantidade saneado")
    
    # Corrigir tipo_movimento invalido
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_movements'"
    ))
    if result.fetchone():
        tipos_str = ", ".join([f"'{t}'" for t in TIPO_MOVIMENTO_VALIDOS])
        conn.execute(text(f"""
            UPDATE stock_movements SET tipo_movimento = 'AJUSTE'
            WHERE tipo_movimento NOT IN ({tipos_str})
        """))
        print("  [OK] stock_movements.tipo_movimento saneado")
    
    # Corrigir status em chamados
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chamados'"
    ))
    if result.fetchone():
        status_str = ", ".join([f"'{s}'" for s in STATUS_CHAMADO_VALIDOS])
        conn.execute(text(f"""
            UPDATE chamados SET status_chamado = 'Finalizado'
            WHERE status_chamado IS NOT NULL AND status_chamado NOT IN ({status_str})
        """))
        print("  [OK] chamados.status_chamado saneado")
    
    print("  [OK] Saneamento SQLite concluido")


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a002] Adicao de Constraints de Integridade")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # ==========================================================================
    # SQLite: SKIP - SQLite nao suporta ALTER TABLE ADD CONSTRAINT
    # ==========================================================================
    if dialect == 'sqlite':
        print("\\n[INFO] SQLite detectado - constraints devem ser definidos na criacao da tabela")
        print("[INFO] Saneamento de dados sera aplicado para consistencia")
        # Apenas aplicar saneamento de dados, não constraints
        _sanitize_data_sqlite(conn)
        print("[OK] Migration a002 concluida (SQLite mode)")
        return

    # ==========================================================================
    # FASE 1: DIAGNOSTICO
    # ==========================================================================

    print("\\n[FASE 1] Diagnostico de dados...")

    # Criar tabela de auditoria de saneamento
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS _migration_a002_sanitization (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100),
            issue_type VARCHAR(100),
            records_affected INTEGER,
            action_taken VARCHAR(200),
            sample_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    issues_found = []

    # 1.1 Duplicidades em tecnico_stock
    if table_exists(conn, 'tecnico_stock'):
        result = conn.execute(text("""
            SELECT tecnico_id, item_lpu_id, COUNT(*) as cnt, SUM(quantidade) as total
            FROM tecnico_stock
            GROUP BY tecnico_id, item_lpu_id
            HAVING COUNT(*) > 1
        """))
        duplicates = result.fetchall()

        if duplicates:
            print(f"  [ISSUE] tecnico_stock: {len(duplicates)} duplicidades encontradas")
            issues_found.append(('tecnico_stock', 'duplicate_keys', len(duplicates)))

            # Registrar amostra
            sample = str(duplicates[:5])
            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('tecnico_stock', 'duplicate_keys', :cnt, 'consolidate_sum', :sample)
            """), {'cnt': len(duplicates), 'sample': sample})
        else:
            print("  [OK] tecnico_stock: sem duplicidades")

    # 1.2 Quantidade invalida em stock_movements
    if table_exists(conn, 'stock_movements'):
        result = conn.execute(text("""
            SELECT COUNT(*), MIN(quantidade), MAX(quantidade)
            FROM stock_movements
            WHERE quantidade IS NULL OR quantidade <= 0
        """))
        row = result.fetchone()
        invalid_qty = row[0]

        if invalid_qty > 0:
            print(f"  [ISSUE] stock_movements.quantidade: {invalid_qty} valores invalidos")
            issues_found.append(('stock_movements', 'invalid_quantity', invalid_qty))

            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('stock_movements', 'invalid_quantity', :cnt, 'set_to_1', :sample)
            """), {'cnt': invalid_qty, 'sample': f'min={row[1]}, max={row[2]}'})
        else:
            print("  [OK] stock_movements.quantidade: todos valores validos")

    # 1.3 Tipo movimento invalido
    if table_exists(conn, 'stock_movements'):
        not_in_tipos = build_not_in_clause(TIPO_MOVIMENTO_VALIDOS)
        result = conn.execute(text(f"""
            SELECT tipo_movimento, COUNT(*) as cnt
            FROM stock_movements
            WHERE tipo_movimento {not_in_tipos}
            GROUP BY tipo_movimento
        """))
        invalid_tipos = result.fetchall()

        if invalid_tipos:
            total = sum(r[1] for r in invalid_tipos)
            print(f"  [ISSUE] stock_movements.tipo_movimento: {total} valores invalidos")
            issues_found.append(('stock_movements', 'invalid_tipo', total))

            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('stock_movements', 'invalid_tipo_movimento', :cnt, 'set_to_AJUSTE', :sample)
            """), {'cnt': total, 'sample': str(invalid_tipos)})
        else:
            print("  [OK] stock_movements.tipo_movimento: todos valores validos")

    # 1.4 Status invalido em solicitacoes_reposicao
    if table_exists(conn, 'solicitacoes_reposicao'):
        not_in_status = build_not_in_clause(STATUS_SOLICITACAO_VALIDOS)
        result = conn.execute(text(f"""
            SELECT status, COUNT(*) as cnt
            FROM solicitacoes_reposicao
            WHERE status {not_in_status}
            GROUP BY status
        """))
        invalid_status = result.fetchall()

        if invalid_status:
            total = sum(r[1] for r in invalid_status)
            print(f"  [ISSUE] solicitacoes_reposicao.status: {total} valores invalidos")
            issues_found.append(('solicitacoes_reposicao', 'invalid_status', total))

            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('solicitacoes_reposicao', 'invalid_status', :cnt, 'set_to_Pendente', :sample)
            """), {'cnt': total, 'sample': str(invalid_status)})
        else:
            print("  [OK] solicitacoes_reposicao.status: todos valores validos")

    # 1.5 Status invalido em chamados
    if table_exists(conn, 'chamados'):
        not_in_status_chamado = build_not_in_clause(STATUS_CHAMADO_VALIDOS)
        result = conn.execute(text(f"""
            SELECT status_chamado, COUNT(*) as cnt
            FROM chamados
            WHERE status_chamado IS NOT NULL
            AND status_chamado {not_in_status_chamado}
            GROUP BY status_chamado
        """))
        invalid_status = result.fetchall()

        if invalid_status:
            total = sum(r[1] for r in invalid_status)
            print(f"  [ISSUE] chamados.status_chamado: {total} valores invalidos")
            issues_found.append(('chamados', 'invalid_status_chamado', total))

            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('chamados', 'invalid_status_chamado', :cnt, 'set_to_Finalizado', :sample)
            """), {'cnt': total, 'sample': str(invalid_status)})
        else:
            print("  [OK] chamados.status_chamado: todos valores validos")

        # status_validacao
        not_in_status_val = build_not_in_clause(STATUS_VALIDACAO_VALIDOS)
        result = conn.execute(text(f"""
            SELECT status_validacao, COUNT(*) as cnt
            FROM chamados
            WHERE status_validacao IS NOT NULL
            AND status_validacao {not_in_status_val}
            GROUP BY status_validacao
        """))
        invalid_status = result.fetchall()

        if invalid_status:
            total = sum(r[1] for r in invalid_status)
            print(f"  [ISSUE] chamados.status_validacao: {total} valores invalidos")
            issues_found.append(('chamados', 'invalid_status_validacao', total))

            conn.execute(text("""
                INSERT INTO _migration_a002_sanitization
                (table_name, issue_type, records_affected, action_taken, sample_data)
                VALUES ('chamados', 'invalid_status_validacao', :cnt, 'set_to_Pendente', :sample)
            """), {'cnt': total, 'sample': str(invalid_status)})
        else:
            print("  [OK] chamados.status_validacao: todos valores validos")

    # ==========================================================================
    # FASE 2: SANEAMENTO
    # ==========================================================================

    if issues_found:
        print(f"\n[FASE 2] Saneamento de {len(issues_found)} problemas encontrados...")
    else:
        print("\n[FASE 2] Nenhum saneamento necessario")

    # 2.1 Consolidar duplicidades em tecnico_stock
    if table_exists(conn, 'tecnico_stock'):
        result = conn.execute(text("""
            SELECT tecnico_id, item_lpu_id, COUNT(*) as cnt
            FROM tecnico_stock
            GROUP BY tecnico_id, item_lpu_id
            HAVING COUNT(*) > 1
        """))
        duplicates = result.fetchall()

        for tecnico_id, item_lpu_id, cnt in duplicates:
            # Calcular soma total
            result = conn.execute(text("""
                SELECT SUM(quantidade), MIN(id)
                FROM tecnico_stock
                WHERE tecnico_id = :tid AND item_lpu_id = :iid
            """), {'tid': tecnico_id, 'iid': item_lpu_id})
            total_qty, keep_id = result.fetchone()

            # Atualizar registro a manter
            conn.execute(text("""
                UPDATE tecnico_stock
                SET quantidade = :qty, data_atualizacao = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {'qty': total_qty or 0, 'id': keep_id})

            # Remover duplicatas
            conn.execute(text("""
                DELETE FROM tecnico_stock
                WHERE tecnico_id = :tid AND item_lpu_id = :iid AND id != :keep
            """), {'tid': tecnico_id, 'iid': item_lpu_id, 'keep': keep_id})

            print(f"  [FIXED] tecnico_stock: consolidado ({tecnico_id}, {item_lpu_id}) -> qty={total_qty}")

    # 2.2 Corrigir quantidade invalida
    if table_exists(conn, 'stock_movements'):
        result = conn.execute(text("""
            UPDATE stock_movements
            SET quantidade = 1
            WHERE quantidade IS NULL OR quantidade <= 0
            RETURNING id
        """))
        fixed = result.fetchall()
        if fixed:
            print(f"  [FIXED] stock_movements.quantidade: {len(fixed)} registros corrigidos para 1")

    # 2.3 Corrigir tipo_movimento invalido
    if table_exists(conn, 'stock_movements'):
        not_in_tipos = build_not_in_clause(TIPO_MOVIMENTO_VALIDOS)
        result = conn.execute(text(f"""
            UPDATE stock_movements
            SET tipo_movimento = 'AJUSTE'
            WHERE tipo_movimento {not_in_tipos}
            RETURNING id, tipo_movimento
        """))
        fixed = result.fetchall()
        if fixed:
            print(f"  [FIXED] stock_movements.tipo_movimento: {len(fixed)} registros corrigidos para AJUSTE")

    # 2.4 Corrigir status em solicitacoes_reposicao
    if table_exists(conn, 'solicitacoes_reposicao'):
        not_in_status = build_not_in_clause(STATUS_SOLICITACAO_VALIDOS)
        result = conn.execute(text(f"""
            UPDATE solicitacoes_reposicao
            SET status = 'Pendente'
            WHERE status {not_in_status}
            RETURNING id
        """))
        fixed = result.fetchall()
        if fixed:
            print(f"  [FIXED] solicitacoes_reposicao.status: {len(fixed)} registros corrigidos para Pendente")

    # 2.5 Corrigir status em chamados
    if table_exists(conn, 'chamados'):
        not_in_status_chamado = build_not_in_clause(STATUS_CHAMADO_VALIDOS)
        result = conn.execute(text(f"""
            UPDATE chamados
            SET status_chamado = 'Finalizado'
            WHERE status_chamado IS NOT NULL
            AND status_chamado {not_in_status_chamado}
            RETURNING id
        """))
        fixed = result.fetchall()
        if fixed:
            print(f"  [FIXED] chamados.status_chamado: {len(fixed)} registros corrigidos para Finalizado")

        not_in_status_val = build_not_in_clause(STATUS_VALIDACAO_VALIDOS)
        result = conn.execute(text(f"""
            UPDATE chamados
            SET status_validacao = 'Pendente'
            WHERE status_validacao IS NOT NULL
            AND status_validacao {not_in_status_val}
            RETURNING id
        """))
        fixed = result.fetchall()
        if fixed:
            print(f"  [FIXED] chamados.status_validacao: {len(fixed)} registros corrigidos para Pendente")

    # ==========================================================================
    # FASE 3: CRIACAO DOS CONSTRAINTS
    # ==========================================================================

    print("\n[FASE 3] Criando constraints...")

    # 3.1 UniqueConstraint em tecnico_stock
    if table_exists(conn, 'tecnico_stock'):
        if not constraint_exists(conn, 'uq_tecnico_stock_tecnico_item'):
            op.create_unique_constraint(
                'uq_tecnico_stock_tecnico_item',
                'tecnico_stock',
                ['tecnico_id', 'item_lpu_id']
            )
            print("  [OK] Criado: uq_tecnico_stock_tecnico_item")
        else:
            print("  [SKIP] uq_tecnico_stock_tecnico_item ja existe")

    # 3.2 CHECK em stock_movements.quantidade
    if table_exists(conn, 'stock_movements'):
        if not constraint_exists(conn, 'ck_stock_movements_quantidade_positive'):
            conn.execute(text("""
                ALTER TABLE stock_movements
                ADD CONSTRAINT ck_stock_movements_quantidade_positive
                CHECK (quantidade > 0)
            """))
            print("  [OK] Criado: ck_stock_movements_quantidade_positive")
        else:
            print("  [SKIP] ck_stock_movements_quantidade_positive ja existe")

    # 3.3 CHECK em stock_movements.tipo_movimento
    if table_exists(conn, 'stock_movements'):
        if not constraint_exists(conn, 'ck_stock_movements_tipo_movimento'):
            tipos_str = ", ".join([f"'{t}'" for t in TIPO_MOVIMENTO_VALIDOS])
            conn.execute(text(f"""
                ALTER TABLE stock_movements
                ADD CONSTRAINT ck_stock_movements_tipo_movimento
                CHECK (tipo_movimento IN ({tipos_str}))
            """))
            print("  [OK] Criado: ck_stock_movements_tipo_movimento")
        else:
            print("  [SKIP] ck_stock_movements_tipo_movimento ja existe")

    # 3.4 CHECK em solicitacoes_reposicao.status
    if table_exists(conn, 'solicitacoes_reposicao'):
        if not constraint_exists(conn, 'ck_solicitacoes_reposicao_status'):
            status_str = ", ".join([f"'{s}'" for s in STATUS_SOLICITACAO_VALIDOS])
            conn.execute(text(f"""
                ALTER TABLE solicitacoes_reposicao
                ADD CONSTRAINT ck_solicitacoes_reposicao_status
                CHECK (status IN ({status_str}))
            """))
            print("  [OK] Criado: ck_solicitacoes_reposicao_status")
        else:
            print("  [SKIP] ck_solicitacoes_reposicao_status ja existe")

    # 3.5 CHECK em chamados.status_chamado
    if table_exists(conn, 'chamados'):
        if not constraint_exists(conn, 'ck_chamados_status_chamado'):
            status_str = ", ".join([f"'{s}'" for s in STATUS_CHAMADO_VALIDOS])
            conn.execute(text(f"""
                ALTER TABLE chamados
                ADD CONSTRAINT ck_chamados_status_chamado
                CHECK (status_chamado IS NULL OR status_chamado IN ({status_str}))
            """))
            print("  [OK] Criado: ck_chamados_status_chamado")
        else:
            print("  [SKIP] ck_chamados_status_chamado ja existe")

    # 3.6 CHECK em chamados.status_validacao
    if table_exists(conn, 'chamados'):
        if not constraint_exists(conn, 'ck_chamados_status_validacao'):
            status_str = ", ".join([f"'{s}'" for s in STATUS_VALIDACAO_VALIDOS])
            conn.execute(text(f"""
                ALTER TABLE chamados
                ADD CONSTRAINT ck_chamados_status_validacao
                CHECK (status_validacao IS NULL OR status_validacao IN ({status_str}))
            """))
            print("  [OK] Criado: ck_chamados_status_validacao")
        else:
            print("  [SKIP] ck_chamados_status_validacao ja existe")

    print("\n" + "=" * 70)
    print("[MIGRATION a002] Constraints aplicados com sucesso")
    print("Relatorio de saneamento salvo em: _migration_a002_sanitization")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()

    print("[MIGRATION a002 DOWNGRADE] Removendo constraints...")

    constraints_to_drop = [
        ('chamados', 'ck_chamados_status_validacao', 'check'),
        ('chamados', 'ck_chamados_status_chamado', 'check'),
        ('solicitacoes_reposicao', 'ck_solicitacoes_reposicao_status', 'check'),
        ('stock_movements', 'ck_stock_movements_tipo_movimento', 'check'),
        ('stock_movements', 'ck_stock_movements_quantidade_positive', 'check'),
        ('tecnico_stock', 'uq_tecnico_stock_tecnico_item', 'unique'),
    ]

    for table, constraint, ctype in constraints_to_drop:
        if table_exists(conn, table) and constraint_exists(conn, constraint):
            conn.execute(text(f"""
                ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}
            """))
            print(f"  [OK] Removido: {constraint}")

    print("[MIGRATION a002 DOWNGRADE] Concluido")
    print("[INFO] Dados saneados NAO sao revertidos")
    print("[INFO] Tabela _migration_a002_sanitization mantida para auditoria")
