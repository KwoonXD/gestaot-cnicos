"""Fix chamados.valor nullable drift

Revision ID: a004
Revises: a003
Create Date: 2026-01-15 10:00:00.000000

OBJETIVO
========
Alinha o campo chamados.valor com o model (nullable=True).
Este campo está deprecated e será removido em fase futura.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a004'
down_revision = 'a003'
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


def column_is_nullable(conn, table_name, column_name):
    """Verifica se coluna é nullable (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        for row in result.fetchall():
            if row[1] == column_name:
                # notnull is in position 3 (1 = NOT NULL, 0 = nullable)
                return row[3] == 0
        return None
    else:
        result = conn.execute(text("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :t AND column_name = :c
        """), {'t': table_name, 'c': column_name})
        row = result.fetchone()
        return row[0] == 'YES' if row else None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a004] Corrigindo nullable de chamados.valor")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # SQLite: Não suporta ALTER COLUMN, e o schema já define nullable no model
    if dialect == 'sqlite':
        print("\\n[INFO] SQLite detectado - ALTER COLUMN não suportado")
        print("[INFO] Em SQLite, o campo já é definido conforme o model na criação")
        print("[OK] Migration a004 concluida (SQLite mode)")
        return

    if not table_exists(conn, 'chamados'):
        print("[SKIP] Tabela chamados não existe")
        return

    # Guard de idempotência: fresh install já cria campo nullable
    if column_is_nullable(conn, 'chamados', 'valor'):
        print("[SKIP] chamados.valor já é nullable (fresh install ou já aplicado)")
        return

    # Tornar campo nullable (alinha com models.py)
    # Isso só executa em ambientes onde o campo era NOT NULL (upgrades)
    print("[ACTION] Alterando chamados.valor para nullable=True...")
    op.alter_column('chamados', 'valor',
                    existing_type=sa.Numeric(precision=10, scale=2),
                    nullable=True)

    print("[OK] chamados.valor agora é nullable")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()

    print("[MIGRATION a004 DOWNGRADE] Revertendo nullable...")

    if not table_exists(conn, 'chamados'):
        return

    # Preencher NULLs com 0 antes de reverter
    conn.execute(text("""
        UPDATE chamados SET valor = 0 WHERE valor IS NULL
    """))

    op.alter_column('chamados', 'valor',
                    existing_type=sa.Numeric(precision=10, scale=2),
                    nullable=False,
                    server_default='0.00')

    print("[OK] chamados.valor revertido para NOT NULL")
