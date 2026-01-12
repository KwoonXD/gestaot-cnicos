#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
migrate_preco_historico.py - Migração para Histórico de Preços de Peças

Cria a tabela itens_lpu_preco_historico para rastrear alterações de preços.

Uso:
    python migrate_preco_historico.py [--check] [--apply]
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
    print("MIGRACAO: Historico de Precos de Pecas")
    print("=" * 60)

    with app.app_context():
        if table_exists('itens_lpu_preco_historico'):
            print("\n[OK] Tabela 'itens_lpu_preco_historico' ja existe.")
            return True

        print("\n[!] Tabela 'itens_lpu_preco_historico' nao existe.")

        if not apply:
            print("\nExecute com --apply para criar a tabela.")
            return False

        print("\n[*] Criando tabela...")

        sql = """
        CREATE TABLE itens_lpu_preco_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_lpu_id INTEGER NOT NULL REFERENCES itens_lpu(id),
            valor_custo_anterior REAL,
            valor_receita_anterior REAL,
            valor_custo_novo REAL,
            valor_receita_novo REAL,
            motivo VARCHAR(200),
            data_alteracao DATETIME DEFAULT CURRENT_TIMESTAMP,
            alterado_por_id INTEGER REFERENCES users(id)
        )
        """

        try:
            db.session.execute(text(sql))
            db.session.commit()
            print("[OK] Tabela criada com sucesso!")

            # Criar índice para buscas por item
            db.session.execute(text(
                "CREATE INDEX idx_preco_hist_item ON itens_lpu_preco_historico(item_lpu_id)"
            ))
            # Criar índice para buscas por data
            db.session.execute(text(
                "CREATE INDEX idx_preco_hist_data ON itens_lpu_preco_historico(data_alteracao)"
            ))
            db.session.commit()
            print("[OK] Indices criados.")

            # Registrar preços iniciais para todos os itens existentes
            from src.models import ItemLPU, ItemLPUPrecoHistorico
            from datetime import datetime

            itens = ItemLPU.query.all()
            registros_iniciais = 0

            for item in itens:
                # Registra o estado inicial (preços atuais)
                if item.valor_custo or item.valor_receita:
                    hist = ItemLPUPrecoHistorico(
                        item_lpu_id=item.id,
                        valor_custo_anterior=None,  # Não há anterior
                        valor_receita_anterior=None,
                        valor_custo_novo=item.valor_custo,
                        valor_receita_novo=item.valor_receita,
                        motivo="Registro inicial (migração)",
                        data_alteracao=datetime.utcnow()
                    )
                    db.session.add(hist)
                    registros_iniciais += 1

            if registros_iniciais > 0:
                db.session.commit()
                print(f"[OK] {registros_iniciais} registro(s) inicial(is) criado(s).")

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
