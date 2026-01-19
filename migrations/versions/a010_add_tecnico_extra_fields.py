"""Add numero, complemento, observacoes fields to tecnicos table

Revision ID: a010
Revises: a009
Create Date: 2026-01-19

Adds numero, complemento, observacoes columns to tecnicos table for complete address and notes.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a010_add_tecnico_extra_fields'
down_revision = 'a009_add_tecnico_address_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Add extra columns to tecnicos table."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    print(f"[MIGRATION a010] Adding numero, complemento, observacoes to tecnicos")
    print(f"[INFO] Dialect: {dialect}")
    
    if dialect == 'sqlite':
        with op.batch_alter_table('tecnicos') as batch_op:
            batch_op.add_column(sa.Column('numero', sa.String(20), nullable=True))
            batch_op.add_column(sa.Column('complemento', sa.String(100), nullable=True))
            batch_op.add_column(sa.Column('observacoes', sa.Text(), nullable=True))
    else:
        op.add_column('tecnicos', sa.Column('numero', sa.String(20), nullable=True))
        op.add_column('tecnicos', sa.Column('complemento', sa.String(100), nullable=True))
        op.add_column('tecnicos', sa.Column('observacoes', sa.Text(), nullable=True))
    
    print("[OK] Migration a010 completed successfully")


def downgrade():
    """Remove extra columns from tecnicos table."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    
    if dialect == 'sqlite':
        with op.batch_alter_table('tecnicos') as batch_op:
            batch_op.drop_column('observacoes')
            batch_op.drop_column('complemento')
            batch_op.drop_column('numero')
    else:
        op.drop_column('tecnicos', 'observacoes')
        op.drop_column('tecnicos', 'complemento')
        op.drop_column('tecnicos', 'numero')
