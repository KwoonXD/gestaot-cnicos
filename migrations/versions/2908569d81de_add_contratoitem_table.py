"""Add ContratoItem table

Revision ID: 2908569d81de
Revises:
Create Date: 2026-01-13 10:06:34.401789

MIGRATION INICIAL DO SISTEMA
============================
Esta migration funciona em dois cenarios:
1. FRESH INSTALL: Cria todo o schema do zero com todas constraints
2. AMBIENTE EXISTENTE: Aplica apenas alteracoes incrementais

A migration e idempotente e tolerante a falhas.

NOTA (2026-01-17): Ajustado para:
  - chamados.valor ser nullable=True (alinhado com model)
  - Fresh install inclui constraints de integridade
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text
from sqlalchemy import inspect


revision = '2908569d81de'
down_revision = None
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Verifica se tabela existe no banco."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = :table_name
        )
    """), {'table_name': table_name})
    return result.scalar()


def column_exists(conn, table_name, column_name):
    """Verifica se coluna existe na tabela."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :table_name
            AND column_name = :column_name
        )
    """), {'table_name': table_name, 'column_name': column_name})
    return result.scalar()


def index_exists(conn, index_name):
    """Verifica se indice existe."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname = :index_name
        )
    """), {'index_name': index_name})
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # ==========================================================================
    # DETECTAR MODO DE OPERACAO
    # ==========================================================================
    is_fresh_install = not table_exists(conn, 'users')

    if is_fresh_install:
        print("[MIGRATION] Modo: FRESH INSTALL - Criando schema completo")
        _create_full_schema(conn)
    else:
        print("[MIGRATION] Modo: AMBIENTE EXISTENTE - Aplicando alteracoes incrementais")
        _apply_incremental_changes(conn)


def _create_full_schema(conn):
    """Cria todo o schema para fresh install."""

    # ==========================================================================
    # TABELAS CORE
    # ==========================================================================

    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='Operador'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )

    op.create_table('clientes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome')
    )

    op.create_table('tecnicos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=200), nullable=False),
        sa.Column('documento', sa.String(length=20), nullable=True),
        sa.Column('contato', sa.String(length=20), nullable=False),
        sa.Column('cidade', sa.String(length=100), nullable=False),
        sa.Column('estado', sa.String(length=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='Ativo'),
        sa.Column('valor_por_atendimento', sa.Numeric(precision=10, scale=2), nullable=True, server_default='120.00'),
        sa.Column('valor_adicional_loja', sa.Numeric(precision=10, scale=2), nullable=True, server_default='20.00'),
        sa.Column('valor_hora_adicional', sa.Numeric(precision=10, scale=2), nullable=True, server_default='30.00'),
        sa.Column('forma_pagamento', sa.String(length=50), nullable=True),
        sa.Column('chave_pagamento', sa.String(length=200), nullable=True),
        sa.Column('tecnico_principal_id', sa.Integer(), nullable=True),
        sa.Column('token_acesso', sa.String(length=36), nullable=True),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('data_cadastro', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tecnico_principal_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('documento'),
        sa.UniqueConstraint('token_acesso')
    )

    op.create_table('pagamentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.Column('periodo_inicio', sa.Date(), nullable=False),
        sa.Column('periodo_fim', sa.Date(), nullable=False),
        sa.Column('valor_por_atendimento', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status_pagamento', sa.String(length=20), nullable=True, server_default='Pendente'),
        sa.Column('data_pagamento', sa.Date(), nullable=True),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('comprovante_path', sa.String(length=255), nullable=True),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ==========================================================================
    # CATALOGO DE SERVICOS
    # ==========================================================================

    op.create_table('catalogo_servicos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('valor_receita', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_custo_tecnico', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('exige_peca', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('paga_tecnico', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('pagamento_integral', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('is_retorno', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('horas_franquia', sa.Integer(), nullable=True, server_default='2'),
        sa.Column('valor_adicional_receita', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_adicional_custo', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_hora_adicional_receita', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_hora_adicional_custo', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default='true'),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ==========================================================================
    # ITENS LPU (PECAS)
    # ==========================================================================

    op.create_table('itens_lpu',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('valor_receita', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_custo', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('itens_lpu_preco_historico',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_lpu_id', sa.Integer(), nullable=False),
        sa.Column('valor_custo_anterior', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('valor_receita_anterior', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('valor_custo_novo', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('valor_receita_novo', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('data_alteracao', sa.DateTime(), nullable=True),
        sa.Column('alterado_por_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['alterado_por_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_itens_lpu_preco_historico_item_lpu_id', 'itens_lpu_preco_historico', ['item_lpu_id'], unique=False)

    # ==========================================================================
    # CONTRATO ITENS (NOVA TABELA)
    # ==========================================================================

    op.create_table('contrato_itens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('item_lpu_id', sa.Integer(), nullable=False),
        sa.Column('valor_venda', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('valor_repasse', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.Column('data_atualizacao', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cliente_id', 'item_lpu_id', name='uq_contrato_item')
    )

    op.create_index('ix_contrato_itens_cliente_id', 'contrato_itens', ['cliente_id'], unique=False)
    op.create_index('ix_contrato_itens_item_lpu_id', 'contrato_itens', ['item_lpu_id'], unique=False)

    # ==========================================================================
    # CHAMADOS
    # ==========================================================================

    op.create_table('chamados',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.Column('codigo_chamado', sa.String(length=100), nullable=True),
        sa.Column('cidade', sa.String(length=100), nullable=False, server_default='Indefinido'),
        sa.Column('loja', sa.String(length=100), nullable=True),
        sa.Column('data_atendimento', sa.Date(), nullable=False),
        sa.Column('catalogo_servico_id', sa.Integer(), nullable=True),
        sa.Column('status_chamado', sa.String(length=20), nullable=True, server_default='Finalizado'),
        sa.Column('is_adicional', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('hora_inicio', sa.String(length=5), nullable=True),
        sa.Column('hora_fim', sa.String(length=5), nullable=True),
        sa.Column('horas_trabalhadas', sa.Float(), nullable=True, server_default='2.0'),
        sa.Column('valor_horas_extras', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_receita_total', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('valor_receita_servico', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('peca_usada', sa.String(length=100), nullable=True),
        sa.Column('valor_receita_peca', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('custo_peca', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('fornecedor_peca', sa.String(length=20), nullable=True, server_default='Empresa'),
        sa.Column('custo_atribuido', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        # DEPRECATED: Campo mantido para compatibilidade. Use custo_atribuido.
        # nullable=True alinhado com models.py (deprecacao fase 1)
        sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'),
        sa.Column('pago', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('pagamento_id', sa.Integer(), nullable=True),
        sa.Column('endereco', sa.Text(), nullable=True),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('fsa_codes', sa.Text(), nullable=True),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.Column('batch_id', sa.String(length=36), nullable=True),
        sa.Column('status_validacao', sa.String(length=20), nullable=True, server_default='Pendente'),
        sa.Column('data_validacao', sa.DateTime(), nullable=True),
        sa.Column('validado_por_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['catalogo_servico_id'], ['catalogo_servicos.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['pagamento_id'], ['pagamentos.id'], ),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
        sa.ForeignKeyConstraint(['validado_por_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_chamados_batch_id', 'chamados', ['batch_id'], unique=False)

    # ==========================================================================
    # TABELAS AUXILIARES
    # ==========================================================================

    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('model_name', sa.String(length=50), nullable=False),
        sa.Column('object_id', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changes', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=50), nullable=False),
        sa.Column('cor', sa.String(length=7), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('saved_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('page_route', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('query_string', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notification_type', sa.String(length=20), nullable=True, server_default='info'),
        sa.Column('is_read', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ==========================================================================
    # GESTAO DE ESTOQUE
    # ==========================================================================

    op.create_table('tecnico_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.Column('item_lpu_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('data_atualizacao', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tecnico_id', 'item_lpu_id', name='uq_tecnico_stock_tecnico_item')
    )

    op.create_table('stock_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_lpu_id', sa.Integer(), nullable=False),
        sa.Column('origem_tecnico_id', sa.Integer(), nullable=True),
        sa.Column('destino_tecnico_id', sa.Integer(), nullable=True),
        sa.Column('chamado_id', sa.Integer(), nullable=True),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('tipo_movimento', sa.String(length=20), nullable=False),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.Column('custo_unitario', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('observacao', sa.String(length=200), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['chamado_id'], ['chamados.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['destino_tecnico_id'], ['tecnicos.id'], ),
        sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
        sa.ForeignKeyConstraint(['origem_tecnico_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_stock_movements_chamado_id', 'stock_movements', ['chamado_id'], unique=False)

    op.create_table('solicitacoes_reposicao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.Column('item_lpu_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='Pendente'),
        sa.Column('justificativa', sa.Text(), nullable=True),
        sa.Column('resposta_admin', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('aprovado_por_id', sa.Integer(), nullable=True),
        sa.Column('data_criacao', sa.DateTime(), nullable=True),
        sa.Column('data_resposta', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['aprovado_por_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ==========================================================================
    # CONSTRAINTS DE INTEGRIDADE (aplicados no fresh install)
    # Garante paridade com migrations a002 aplicadas em ambiente existente
    # ==========================================================================

    print("[MIGRATION] Aplicando constraints de integridade no fresh install...")

    # CHECK quantidade > 0 em stock_movements
    conn.execute(text("""
        ALTER TABLE stock_movements
        ADD CONSTRAINT ck_stock_movements_quantidade_positive
        CHECK (quantidade > 0)
    """))

    # CHECK tipo_movimento valido
    conn.execute(text("""
        ALTER TABLE stock_movements
        ADD CONSTRAINT ck_stock_movements_tipo_movimento
        CHECK (tipo_movimento IN ('ENVIO', 'USO', 'DEVOLUCAO', 'AJUSTE', 'CORRECAO'))
    """))

    # CHECK status valido em solicitacoes_reposicao
    conn.execute(text("""
        ALTER TABLE solicitacoes_reposicao
        ADD CONSTRAINT ck_solicitacoes_reposicao_status
        CHECK (status IN ('Pendente', 'Aprovada', 'Enviada', 'Recusada', 'Cancelada'))
    """))

    # CHECK status_chamado valido
    conn.execute(text("""
        ALTER TABLE chamados
        ADD CONSTRAINT ck_chamados_status_chamado
        CHECK (status_chamado IS NULL OR status_chamado IN (
            'Finalizado', 'Concluído', 'Cancelado', 'Pendente', 'SPARE', 'Em Andamento'
        ))
    """))

    # CHECK status_validacao valido
    conn.execute(text("""
        ALTER TABLE chamados
        ADD CONSTRAINT ck_chamados_status_validacao
        CHECK (status_validacao IS NULL OR status_validacao IN (
            'Pendente', 'Aprovado', 'Rejeitado'
        ))
    """))

    print("[MIGRATION] Fresh install concluido com sucesso (schema + constraints)")


def _apply_incremental_changes(conn):
    """Aplica alteracoes incrementais em ambiente existente."""

    # ==========================================================================
    # 1. CRIAR TABELA CONTRATO_ITENS (se nao existir)
    # ==========================================================================

    if not table_exists(conn, 'contrato_itens'):
        print("[MIGRATION] Criando tabela contrato_itens...")
        op.create_table('contrato_itens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cliente_id', sa.Integer(), nullable=False),
            sa.Column('item_lpu_id', sa.Integer(), nullable=False),
            sa.Column('valor_venda', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('valor_repasse', sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=True, server_default='true'),
            sa.Column('data_criacao', sa.DateTime(), nullable=True),
            sa.Column('data_atualizacao', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
            sa.ForeignKeyConstraint(['item_lpu_id'], ['itens_lpu.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cliente_id', 'item_lpu_id', name='uq_contrato_item')
        )

        op.create_index('ix_contrato_itens_cliente_id', 'contrato_itens', ['cliente_id'], unique=False)
        op.create_index('ix_contrato_itens_item_lpu_id', 'contrato_itens', ['item_lpu_id'], unique=False)
    else:
        print("[MIGRATION] Tabela contrato_itens ja existe, pulando...")

    # ==========================================================================
    # 2. ARQUIVAR E REMOVER TABELA LANCAMENTOS (se existir)
    # ==========================================================================

    if table_exists(conn, 'lancamentos'):
        print("[MIGRATION] Arquivando tabela lancamentos...")

        # Contar registros
        result = conn.execute(text("SELECT COUNT(*) FROM lancamentos"))
        count = result.scalar()

        if count > 0:
            # Criar tabela de arquivo
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS lancamentos_archive (
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    id INTEGER,
                    tecnico_id INTEGER,
                    pagamento_id INTEGER,
                    data DATE,
                    tipo VARCHAR(20),
                    valor NUMERIC(10, 2),
                    descricao VARCHAR(200),
                    data_criacao TIMESTAMP,
                    chamado_id INTEGER
                )
            """))

            # Copiar dados
            conn.execute(text("""
                INSERT INTO lancamentos_archive (
                    id, tecnico_id, pagamento_id, data, tipo, valor,
                    descricao, data_criacao, chamado_id
                )
                SELECT id, tecnico_id, pagamento_id, data, tipo, valor,
                       descricao, data_criacao, chamado_id
                FROM lancamentos
            """))
            print(f"[MIGRATION] Arquivados {count} registros em lancamentos_archive")

        # Remover tabela original
        op.drop_table('lancamentos')
        print("[MIGRATION] Tabela lancamentos removida")
    else:
        print("[MIGRATION] Tabela lancamentos nao existe, pulando...")

    # ==========================================================================
    # 3. PADRONIZAR INDICES (tolerante a falhas)
    # ==========================================================================

    # itens_lpu_preco_historico: renomear indices
    if index_exists(conn, 'idx_preco_hist_data'):
        op.drop_index('idx_preco_hist_data', table_name='itens_lpu_preco_historico')

    if index_exists(conn, 'idx_preco_hist_item'):
        op.drop_index('idx_preco_hist_item', table_name='itens_lpu_preco_historico')

    if not index_exists(conn, 'ix_itens_lpu_preco_historico_item_lpu_id'):
        op.create_index('ix_itens_lpu_preco_historico_item_lpu_id', 'itens_lpu_preco_historico', ['item_lpu_id'], unique=False)

    # solicitacoes_reposicao: remover indices antigos
    if index_exists(conn, 'idx_solicit_status'):
        op.drop_index('idx_solicit_status', table_name='solicitacoes_reposicao')

    if index_exists(conn, 'idx_solicit_tecnico'):
        op.drop_index('idx_solicit_tecnico', table_name='solicitacoes_reposicao')

    # stock_movements: renomear indice
    if index_exists(conn, 'idx_stockmov_chamado'):
        op.drop_index('idx_stockmov_chamado', table_name='stock_movements')

    if not index_exists(conn, 'ix_stock_movements_chamado_id'):
        op.create_index('ix_stock_movements_chamado_id', 'stock_movements', ['chamado_id'], unique=False)

    # ==========================================================================
    # 4. REMOVER COLUNA LEGADA (tolerante)
    # ==========================================================================

    if column_exists(conn, 'tecnicos', 'saldo_atual'):
        print("[MIGRATION] Removendo coluna tecnicos.saldo_atual...")
        with op.batch_alter_table('tecnicos', schema=None) as batch_op:
            batch_op.drop_column('saldo_atual')
    else:
        print("[MIGRATION] Coluna tecnicos.saldo_atual nao existe, pulando...")

    print("[MIGRATION] Alteracoes incrementais concluidas")


def downgrade():
    conn = op.get_bind()

    # ==========================================================================
    # DETECTAR MODO
    # ==========================================================================
    was_fresh_install = not table_exists(conn, 'lancamentos_archive')

    if was_fresh_install:
        print("[MIGRATION DOWNGRADE] Removendo schema completo...")
        _drop_full_schema(conn)
    else:
        print("[MIGRATION DOWNGRADE] Revertendo alteracoes incrementais...")
        _revert_incremental_changes(conn)


def _drop_full_schema(conn):
    """Remove todo o schema (fresh install downgrade)."""

    # Ordem inversa de criacao (dependencias)
    tables_to_drop = [
        'solicitacoes_reposicao',
        'stock_movements',
        'tecnico_stock',
        'notifications',
        'saved_views',
        'tags',
        'audit_logs',
        'chamados',
        'contrato_itens',
        'itens_lpu_preco_historico',
        'itens_lpu',
        'catalogo_servicos',
        'pagamentos',
        'tecnicos',
        'clientes',
        'users',
    ]

    for table in tables_to_drop:
        if table_exists(conn, table):
            op.drop_table(table)

    print("[MIGRATION DOWNGRADE] Schema removido")


def _revert_incremental_changes(conn):
    """Reverte alteracoes incrementais."""

    # Restaurar coluna saldo_atual
    if not column_exists(conn, 'tecnicos', 'saldo_atual'):
        with op.batch_alter_table('tecnicos', schema=None) as batch_op:
            batch_op.add_column(sa.Column('saldo_atual', sa.FLOAT(), nullable=True))

    # Restaurar indices antigos
    if not index_exists(conn, 'idx_stockmov_chamado'):
        if index_exists(conn, 'ix_stock_movements_chamado_id'):
            op.drop_index('ix_stock_movements_chamado_id', table_name='stock_movements')
        op.create_index('idx_stockmov_chamado', 'stock_movements', ['chamado_id'], unique=False)

    if not index_exists(conn, 'idx_solicit_tecnico'):
        op.create_index('idx_solicit_tecnico', 'solicitacoes_reposicao', ['tecnico_id'], unique=False)

    if not index_exists(conn, 'idx_solicit_status'):
        op.create_index('idx_solicit_status', 'solicitacoes_reposicao', ['status'], unique=False)

    if not index_exists(conn, 'idx_preco_hist_item'):
        if index_exists(conn, 'ix_itens_lpu_preco_historico_item_lpu_id'):
            op.drop_index('ix_itens_lpu_preco_historico_item_lpu_id', table_name='itens_lpu_preco_historico')
        op.create_index('idx_preco_hist_item', 'itens_lpu_preco_historico', ['item_lpu_id'], unique=False)
        op.create_index('idx_preco_hist_data', 'itens_lpu_preco_historico', ['data_alteracao'], unique=False)

    # Restaurar tabela lancamentos do arquivo
    if table_exists(conn, 'lancamentos_archive') and not table_exists(conn, 'lancamentos'):
        op.create_table('lancamentos',
            sa.Column('id', sa.INTEGER(), nullable=False),
            sa.Column('tecnico_id', sa.INTEGER(), nullable=False),
            sa.Column('pagamento_id', sa.INTEGER(), nullable=True),
            sa.Column('data', sa.DATE(), nullable=False),
            sa.Column('tipo', sa.VARCHAR(length=20), nullable=False),
            sa.Column('valor', sa.NUMERIC(precision=10, scale=2), nullable=False),
            sa.Column('descricao', sa.VARCHAR(length=200), nullable=False),
            sa.Column('data_criacao', sa.DATETIME(), nullable=True),
            sa.Column('chamado_id', sa.INTEGER(), nullable=True),
            sa.ForeignKeyConstraint(['chamado_id'], ['chamados.id'], ),
            sa.ForeignKeyConstraint(['pagamento_id'], ['pagamentos.id'], ),
            sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        conn.execute(text("""
            INSERT INTO lancamentos (
                id, tecnico_id, pagamento_id, data, tipo, valor,
                descricao, data_criacao, chamado_id
            )
            SELECT id, tecnico_id, pagamento_id, data, tipo, valor,
                   descricao, data_criacao, chamado_id
            FROM lancamentos_archive
        """))
        print("[MIGRATION DOWNGRADE] Tabela lancamentos restaurada do arquivo")

    # Remover tabela contrato_itens
    if table_exists(conn, 'contrato_itens'):
        if index_exists(conn, 'ix_contrato_itens_item_lpu_id'):
            op.drop_index('ix_contrato_itens_item_lpu_id', table_name='contrato_itens')
        if index_exists(conn, 'ix_contrato_itens_cliente_id'):
            op.drop_index('ix_contrato_itens_cliente_id', table_name='contrato_itens')
        op.drop_table('contrato_itens')

    print("[MIGRATION DOWNGRADE] Alteracoes revertidas")
