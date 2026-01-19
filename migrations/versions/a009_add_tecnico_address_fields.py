"""Add address fields to tecnicos table

Revision ID: a009
Revises: a008
Create Date: 2026-01-19

Adds cep, logradouro, bairro columns to tecnicos table for complete address storage.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a009_add_tecnico_address_fields'
down_revision = 'a008'  # Matches a008's revision ID
branch_labels = None
depends_on = None


def upgrade():
    """Add address columns to tecnicos table."""
    # Detect dialect
    bind = op.get_bind()
    dialect = bind.dialect.name
    print(f"[MIGRATION a009] Adding address fields to tecnicos table")
    print(f"[INFO] Dialect: {dialect}")
    
    if dialect == 'sqlite':
        # SQLite: batch mode required for adding columns
        with op.batch_alter_table('tecnicos') as batch_op:
            batch_op.add_column(sa.Column('cep', sa.String(10), nullable=True))
            batch_op.add_column(sa.Column('logradouro', sa.String(200), nullable=True))
            batch_op.add_column(sa.Column('bairro', sa.String(100), nullable=True))
    else:
        # PostgreSQL and others
        op.add_column('tecnicos', sa.Column('cep', sa.String(10), nullable=True))
        op.add_column('tecnicos', sa.Column('logradouro', sa.String(200), nullable=True))
        op.add_column('tecnicos', sa.Column('bairro', sa.String(100), nullable=True))
    
    print("[OK] Migration a009 completed successfully")


def downgrade():
    """Remove address columns from tecnicos table."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    
    if dialect == 'sqlite':
        with op.batch_alter_table('tecnicos') as batch_op:
            batch_op.drop_column('bairro')
            batch_op.drop_column('logradouro')
            batch_op.drop_column('cep')
    else:
        op.drop_column('tecnicos', 'bairro')
        op.drop_column('tecnicos', 'logradouro')
        op.drop_column('tecnicos', 'cep')
