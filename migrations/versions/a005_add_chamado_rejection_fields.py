"""Add chamado rejection fields for soft delete

Revision ID: a005
Revises: a004
Create Date: 2026-01-17 17:50:00.000000

OBJETIVO
========
Adiciona campos para suportar soft delete de chamados rejeitados:
- motivo_rejeicao: Texto explicando por que foi rejeitado
- data_rejeicao: Timestamp da rejeição
- rejeitado_por_id: FK para User que rejeitou

Isso elimina o HARD DELETE que causava IntegrityError com FKs do StockMovement.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a005'
down_revision = 'a004'
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


def column_exists(conn, table_name, column_name):
    """Verifica se coluna existe (SQLite + PostgreSQL)."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns
    else:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = :t AND column_name = :c
            )
        """), {'t': table_name, 'c': column_name})
        return result.scalar()


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a005] Adicao de campos para soft delete de chamados")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    if not table_exists(conn, 'chamados'):
        print("[SKIP] Tabela chamados nao existe")
        return

    # Adicionar motivo_rejeicao
    if not column_exists(conn, 'chamados', 'motivo_rejeicao'):
        op.add_column('chamados', sa.Column('motivo_rejeicao', sa.Text, nullable=True))
        print("[OK] Adicionado: chamados.motivo_rejeicao")
    else:
        print("[SKIP] chamados.motivo_rejeicao ja existe")

    # Adicionar data_rejeicao
    if not column_exists(conn, 'chamados', 'data_rejeicao'):
        op.add_column('chamados', sa.Column('data_rejeicao', sa.DateTime, nullable=True))
        print("[OK] Adicionado: chamados.data_rejeicao")
    else:
        print("[SKIP] chamados.data_rejeicao ja existe")

    # Adicionar rejeitado_por_id
    if not column_exists(conn, 'chamados', 'rejeitado_por_id'):
        op.add_column('chamados', sa.Column('rejeitado_por_id', sa.Integer, nullable=True))
        # FK só no PostgreSQL (SQLite não suporta ALTER TABLE ADD CONSTRAINT)
        if dialect != 'sqlite':
            op.create_foreign_key(
                'fk_chamados_rejeitado_por',
                'chamados', 'users',
                ['rejeitado_por_id'], ['id']
            )
        print("[OK] Adicionado: chamados.rejeitado_por_id")
    else:
        print("[SKIP] chamados.rejeitado_por_id ja existe")

    print("=" * 70)
    print("[MIGRATION a005] Concluida com sucesso")
    print("=" * 70)


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("[MIGRATION a005 DOWNGRADE] Removendo campos de rejeicao...")

    # Remover FK primeiro (PostgreSQL)
    if dialect != 'sqlite':
        try:
            op.drop_constraint('fk_chamados_rejeitado_por', 'chamados', type_='foreignkey')
        except Exception:
            pass

    # Remover colunas
    try:
        op.drop_column('chamados', 'rejeitado_por_id')
    except Exception:
        pass

    try:
        op.drop_column('chamados', 'data_rejeicao')
    except Exception:
        pass

    try:
        op.drop_column('chamados', 'motivo_rejeicao')
    except Exception:
        pass

    print("[OK] Campos removidos")
