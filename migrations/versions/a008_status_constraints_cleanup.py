"""Consolidate status CHECK constraints (cleanup)

Revision ID: a008
Revises: a007
Create Date: 2026-01-19 10:18:00.000000

OBJETIVO
========
Consolidar e corrigir as CHECK constraints de status na tabela chamados,
eliminando duplicidade e conflito entre migrations antigas (a002 vs a006).

PROBLEMA HISTORICO
==================
- a002: Criou ck_chamados_status_validacao SEM 'Excluído'
- a006: Criou chk_chamados_status_validacao COM 'Excluído' (prefixo diferente)
- a007: Tentou consolidar mas usou try/except pass (pode ter falhado silenciosamente)

Algumas bases podem ter: ck_*, chk_*, ambas, ou nenhuma constraint.
O soft delete (status_validacao='Excluído') falhava se ck_* ainda existisse.

SOLUCAO
=======
Esta migration:
1. Dropa TODAS as variantes conhecidas de constraints (idempotente)
2. Cria constraints canônicas com nomes padronizados (ck_*)
3. Permite NULL (comportamento existente)

VALORES CANONICOS
=================
- status_validacao: Pendente, Aprovado, Rejeitado, Excluído
- status_chamado: Pendente, Em Andamento, Concluído, SPARE, Cancelado

NOTA: 'Finalizado' foi excluído pois a007 já migrou todos para 'Concluído'.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a008'
down_revision = 'a007'
branch_labels = None
depends_on = None


# Valores canônicos (fonte da verdade)
STATUS_VALIDACAO_CANONICO = ['Pendente', 'Aprovado', 'Rejeitado', 'Excluído']
STATUS_CHAMADO_CANONICO = ['Pendente', 'Em Andamento', 'Concluído', 'SPARE', 'Cancelado']

# Todos os nomes de constraints conhecidos (de migrations anteriores)
CONSTRAINTS_TO_DROP = [
    'ck_chamados_status_validacao',
    'chk_chamados_status_validacao', 
    'ck_chamados_status_chamado',
    'chk_chamados_status_chamado',
]


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a008] Status Constraints Cleanup")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # SQLite: Skip constraint management (não suporta ALTER TABLE ADD CONSTRAINT)
    if dialect == 'sqlite':
        print("[INFO] SQLite detectado - constraints não são gerenciados")
        print("[OK] Migration a008 concluída (SQLite mode)")
        return

    # ==========================================================================
    # FASE 1: DIAGNOSTICO
    # ==========================================================================
    print("\n[FASE 1] Diagnóstico de constraints existentes...")

    # Listar constraints atuais
    result = conn.execute(text("""
        SELECT conname, pg_get_constraintdef(oid) as def
        FROM pg_constraint 
        WHERE conrelid = 'chamados'::regclass 
        AND conname LIKE '%status%'
    """))
    existing = result.fetchall()
    
    if existing:
        for name, definition in existing:
            print(f"  [FOUND] {name}: {definition}")
    else:
        print("  [INFO] Nenhuma constraint de status encontrada")

    # Verificar dados existentes
    print("\n[FASE 1.1] Verificando valores existentes...")
    
    # status_validacao
    result = conn.execute(text("""
        SELECT status_validacao, COUNT(*) as cnt
        FROM chamados
        WHERE status_validacao IS NOT NULL
        GROUP BY status_validacao
        ORDER BY cnt DESC
    """))
    val_stats = result.fetchall()
    print("  status_validacao:")
    for val, cnt in val_stats:
        marker = "✓" if val in STATUS_VALIDACAO_CANONICO else "⚠ UNEXPECTED"
        print(f"    {marker} '{val}': {cnt} registros")

    # status_chamado
    result = conn.execute(text("""
        SELECT status_chamado, COUNT(*) as cnt
        FROM chamados
        WHERE status_chamado IS NOT NULL
        GROUP BY status_chamado
        ORDER BY cnt DESC
    """))
    chamado_stats = result.fetchall()
    print("  status_chamado:")
    for val, cnt in chamado_stats:
        marker = "✓" if val in STATUS_CHAMADO_CANONICO else "⚠ UNEXPECTED"
        print(f"    {marker} '{val}': {cnt} registros")

    # ==========================================================================
    # FASE 2: SANEAMENTO DE DADOS (se necessário)
    # ==========================================================================
    print("\n[FASE 2] Saneamento de dados...")

    # Migrar 'Finalizado' -> 'Concluído' (caso a007 tenha falhado)
    result = conn.execute(text("""
        UPDATE chamados 
        SET status_chamado = 'Concluído' 
        WHERE status_chamado = 'Finalizado'
        RETURNING id
    """))
    fixed = result.fetchall()
    if fixed:
        print(f"  [FIXED] {len(fixed)} chamados com 'Finalizado' -> 'Concluído'")
    else:
        print("  [OK] Nenhum 'Finalizado' encontrado")

    # Verificar valores inesperados em status_validacao
    valid_vals_str = ", ".join([f"'{v}'" for v in STATUS_VALIDACAO_CANONICO])
    result = conn.execute(text(f"""
        SELECT DISTINCT status_validacao 
        FROM chamados 
        WHERE status_validacao IS NOT NULL 
        AND status_validacao NOT IN ({valid_vals_str})
    """))
    unexpected_validacao = result.fetchall()
    if unexpected_validacao:
        print(f"  [WARN] Valores inesperados em status_validacao: {[v[0] for v in unexpected_validacao]}")
        print("  [WARN] Convertendo para 'Pendente' para permitir constraint...")
        conn.execute(text(f"""
            UPDATE chamados 
            SET status_validacao = 'Pendente' 
            WHERE status_validacao IS NOT NULL 
            AND status_validacao NOT IN ({valid_vals_str})
        """))

    # Verificar valores inesperados em status_chamado
    valid_chamado_str = ", ".join([f"'{v}'" for v in STATUS_CHAMADO_CANONICO])
    result = conn.execute(text(f"""
        SELECT DISTINCT status_chamado 
        FROM chamados 
        WHERE status_chamado IS NOT NULL 
        AND status_chamado NOT IN ({valid_chamado_str})
    """))
    unexpected_chamado = result.fetchall()
    if unexpected_chamado:
        print(f"  [WARN] Valores inesperados em status_chamado: {[v[0] for v in unexpected_chamado]}")
        print("  [WARN] Convertendo para 'Concluído' para permitir constraint...")
        conn.execute(text(f"""
            UPDATE chamados 
            SET status_chamado = 'Concluído' 
            WHERE status_chamado IS NOT NULL 
            AND status_chamado NOT IN ({valid_chamado_str})
        """))

    # ==========================================================================
    # FASE 3: DROP CONSTRAINTS (idempotente)
    # ==========================================================================
    print("\n[FASE 3] Removendo constraints duplicadas...")

    for constraint_name in CONSTRAINTS_TO_DROP:
        # DROP IF EXISTS é idempotente
        conn.execute(text(f"""
            ALTER TABLE chamados DROP CONSTRAINT IF EXISTS {constraint_name}
        """))
        print(f"  [DROP] {constraint_name} (if exists)")

    # ==========================================================================
    # FASE 4: CREATE CONSTRAINTS CANONICAS
    # ==========================================================================
    print("\n[FASE 4] Criando constraints canônicas...")

    # status_validacao
    vals_str = ", ".join([f"'{v}'" for v in STATUS_VALIDACAO_CANONICO])
    conn.execute(text(f"""
        ALTER TABLE chamados
        ADD CONSTRAINT ck_chamados_status_validacao
        CHECK (status_validacao IS NULL OR status_validacao IN ({vals_str}))
    """))
    print(f"  [OK] ck_chamados_status_validacao: {STATUS_VALIDACAO_CANONICO}")

    # status_chamado
    chamado_str = ", ".join([f"'{v}'" for v in STATUS_CHAMADO_CANONICO])
    conn.execute(text(f"""
        ALTER TABLE chamados
        ADD CONSTRAINT ck_chamados_status_chamado
        CHECK (status_chamado IS NULL OR status_chamado IN ({chamado_str}))
    """))
    print(f"  [OK] ck_chamados_status_chamado: {STATUS_CHAMADO_CANONICO}")

    # ==========================================================================
    # FASE 5: VALIDACAO
    # ==========================================================================
    print("\n[FASE 5] Validação final...")

    result = conn.execute(text("""
        SELECT conname, pg_get_constraintdef(oid) as def
        FROM pg_constraint 
        WHERE conrelid = 'chamados'::regclass 
        AND conname LIKE '%status%'
    """))
    final_constraints = result.fetchall()
    
    print("  Constraints finais:")
    for name, definition in final_constraints:
        print(f"    {name}: {definition}")

    expected_count = 2
    if len(final_constraints) == expected_count:
        print(f"\n  [OK] Exatamente {expected_count} constraints de status (esperado)")
    else:
        print(f"\n  [WARN] {len(final_constraints)} constraints encontradas (esperado: {expected_count})")

    print("\n" + "=" * 70)
    print("[MIGRATION a008] Constraints consolidadas com sucesso!")
    print("Soft delete (status_validacao='Excluído') agora permitido.")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("[MIGRATION a008 DOWNGRADE] Removendo constraints canônicas...")

    if dialect == 'sqlite':
        print("[INFO] SQLite - nada a fazer")
        return

    # Remove apenas as constraints canônicas criadas por esta migration
    conn.execute(text("""
        ALTER TABLE chamados DROP CONSTRAINT IF EXISTS ck_chamados_status_validacao
    """))
    conn.execute(text("""
        ALTER TABLE chamados DROP CONSTRAINT IF EXISTS ck_chamados_status_chamado
    """))

    print("[OK] Constraints removidas")
    print("[INFO] Downgrade não recria constraints antigas (seria inseguro)")
    print("[INFO] Para restaurar constraints, rode 'flask db upgrade' novamente")
