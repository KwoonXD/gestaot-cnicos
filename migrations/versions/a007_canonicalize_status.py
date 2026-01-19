"""Canonicalize status 'Finalizado' to 'Concluído'

Revision ID: a007
Revises: a006
Create Date: 2026-01-17 19:30:00.000000

OBJETIVO
========
Migra todos os chamados com status 'Finalizado' para 'Concluído'.
Remove 'Finalizado' da lista de status válidos (CHECK constraint).

OBS: Se for SQLite, não atualizamos a CHECK constraint complexa
(demanda recriação de tabela), mas atualizamos os dados.
Para Postgres, atualizamos a constraint.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

revision = 'a007'
down_revision = 'a006'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    
    print("[MIGRATION a007] Canonicalizando status 'Finalizado' -> 'Concluído'")
    
    # 1. Update Data
    # Use text() explicitly for raw SQL
    op.execute(text("UPDATE chamados SET status_chamado = 'Concluído' WHERE status_chamado = 'Finalizado'"))
    print("[OK] Dados atualizados.")
    
    # 2. Update Constraint (Postgres only)
    if dialect != 'sqlite':
        try:
            # Drop old constraints (from a006 AND a002) to consolidate
            # a006 uses 'chk_', a002 uses 'ck_'
            # We try to drop both to ensure clean state
            
            # 1. status_chamado
            try:
                op.drop_constraint("chk_chamados_status_chamado", "chamados", type_='check')
                print("[OK] chk_chamados_status_chamado removida")
            except: pass
            
            try:
                op.drop_constraint("ck_chamados_status_chamado", "chamados", type_='check')
                print("[OK] ck_chamados_status_chamado removida")
            except: pass
            
            # Create new constraint (Consolidated)
            valid_status = ['Pendente', 'Em Andamento', 'Concluído', 'SPARE', 'Cancelado']
            check_sql = f"status_chamado IN ({', '.join([repr(s) for s in valid_status])})"
            
            op.create_check_constraint(
                "chk_chamados_status_chamado",
                "chamados",
                text(check_sql)
            )
            print("[OK] Constraint chk_chamados_status_chamado recriada e consolidada.")

            # 2. status_validacao
            try:
                op.drop_constraint("chk_chamados_status_validacao", "chamados", type_='check')
                print("[OK] chk_chamados_status_validacao removida")
            except: pass
            
            try:
                # a002 used 'ck_chamados_status_validacao'
                op.drop_constraint("ck_chamados_status_validacao", "chamados", type_='check')
                print("[OK] ck_chamados_status_validacao removida")
            except: pass
            
            valid_validacao = ['Pendente', 'Aprovado', 'Rejeitado', 'Excluído']
            check_val_sql = f"status_validacao IN ({', '.join([repr(s) for s in valid_validacao])})"
             
            op.create_check_constraint(
                "chk_chamados_status_validacao",
                "chamados",
                text(check_val_sql)
            )
            print("[OK] Constraint chk_chamados_status_validacao recriada e consolidada.")
            
        except Exception as e:
            print(f"[WARN] Falha ao atualizar constraint: {e}")

def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    
    # Revert Constraint
    if dialect != 'sqlite':
        try:
            op.drop_constraint("chk_chamados_status_chamado", "chamados", type_='check')
            valid_status = ['Pendente', 'Em Andamento', 'Concluído', 'SPARE', 'Cancelado', 'Finalizado']
            check_sql = f"status_chamado IN ({', '.join([repr(s) for s in valid_status])})"
            op.create_check_constraint(
                "chk_chamados_status_chamado",
                "chamados",
                text(check_sql)
            )
            print("[OK] Constraint revertida para incluir 'Finalizado'")
        except:
            pass
            
    # NOTE: Does NOT revert data update (irreversible logic without backup)
