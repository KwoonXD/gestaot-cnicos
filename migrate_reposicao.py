#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
migrate_reposicao.py - Migração para Sistema de Solicitação de Reposição

Cria a tabela solicitacoes_reposicao para gerenciar pedidos de reposição de estoque.

Uso:
    python migrate_reposicao.py [--check] [--apply]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import create_app, db
from sqlalchemy import text, inspect

app = create_app()


def table_exists(table_name):
    """Verifica se uma tabela existe."""
    with app.app_context():
        inspector = inspect(db.engine)
        return table_name in inspector.get_table_names()


def run_migration(apply=False):
    print("\n" + "=" * 60)
    print("MIGRACAO: Sistema de Solicitacao de Reposicao")
    print("=" * 60)

    with app.app_context():
        if table_exists('solicitacoes_reposicao'):
            print("\n[OK] Tabela 'solicitacoes_reposicao' ja existe.")
            return True

        print("\n[!] Tabela 'solicitacoes_reposicao' nao existe.")

        if not apply:
            print("\nExecute com --apply para criar a tabela.")
            return False

        print("\n[*] Criando tabela...")

        sql = """
        CREATE TABLE solicitacoes_reposicao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tecnico_id INTEGER NOT NULL REFERENCES tecnicos(id),
            item_lpu_id INTEGER NOT NULL REFERENCES itens_lpu(id),
            quantidade INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(20) DEFAULT 'Pendente',
            justificativa TEXT,
            resposta_admin TEXT,
            created_by_id INTEGER REFERENCES users(id),
            aprovado_por_id INTEGER REFERENCES users(id),
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            data_resposta DATETIME
        )
        """

        try:
            db.session.execute(text(sql))
            db.session.commit()
            print("[OK] Tabela criada com sucesso!")

            # Criar índices
            db.session.execute(text(
                "CREATE INDEX idx_solicit_status ON solicitacoes_reposicao(status)"
            ))
            db.session.execute(text(
                "CREATE INDEX idx_solicit_tecnico ON solicitacoes_reposicao(tecnico_id)"
            ))
            db.session.commit()
            print("[OK] Indices criados.")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"[ERRO] {e}")
            return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    if args.apply:
        run_migration(apply=True)
    else:
        run_migration(apply=False)
