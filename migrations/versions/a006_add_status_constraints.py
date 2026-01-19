"""Add status constraints (Enums)

Revision ID: a006
Revises: a005
Create Date: 2026-01-17 19:15:00.000000

OBJETIVO
========
Adiciona CHECK constraints para garantir integridade dos campos de status:

1. status_chamado:
   - 'Pendente'
   - 'Em Andamento'
   - 'Concluído'
   - 'SPARE'
   - 'Cancelado'
   - 'Finalizado' (Legacy)

2. status_validacao:
   - 'Pendente'
   - 'Aprovado'
   - 'Rejeitado'
   - 'Excluído'

Isso impede que valores inválidos sejam inseridos diretamente no banco.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = 'a006'
down_revision = 'a005'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    print("=" * 70)
    print("[MIGRATION a006] Adicao de CHECK constraints para status")
    print(f"[INFO] Dialeto: {dialect}")
    print("=" * 70)

    # 1. status_chamado
    # -----------------
    valid_status_chamado = [
        'Pendente', 'Em Andamento', 'Concluído', 'SPARE', 
        'Cancelado', 'Finalizado'
    ]
    status_chamado_check = f"status_chamado IN ({', '.join([repr(s) for s in valid_status_chamado])})"
    
    # SQLite não suporta ALTER TABLE ADD CONSTRAINT facilmente
    if dialect != 'sqlite':
        try:
            op.create_check_constraint(
                "chk_chamados_status_chamado",
                "chamados",
                text(status_chamado_check)
            )
            print("[OK] Constraint chk_chamados_status_chamado criada")
        except Exception as e:
            print(f"[WARN] Erro ao criar constraint status_chamado (pode ja existir): {e}")

    # 2. status_validacao
    # -------------------
    valid_status_validacao = [
        'Pendente', 'Aprovado', 'Rejeitado', 'Excluído'
    ]
    status_validacao_check = f"status_validacao IN ({', '.join([repr(s) for s in valid_status_validacao])})"
    
    if dialect != 'sqlite':
        try:
            op.create_check_constraint(
                "chk_chamados_status_validacao",
                "chamados",
                text(status_validacao_check)
            )
            print("[OK] Constraint chk_chamados_status_validacao criada")
        except Exception as e:
            print(f"[WARN] Erro ao criar constraint status_validacao (pode ja existir): {e}")

    print("=" * 70)
    print("[MIGRATION a006] Concluida com sucesso")


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    
    if dialect != 'sqlite':
        try:
            op.drop_constraint("chk_chamados_status_chamado", "chamados", type_='check')
            print("[OK] Constraint chk_chamados_status_chamado removida")
        except:
            pass
            
        try:
            op.drop_constraint("chk_chamados_status_validacao", "chamados", type_='check')
            print("[OK] Constraint chk_chamados_status_validacao removida")
        except:
            pass
