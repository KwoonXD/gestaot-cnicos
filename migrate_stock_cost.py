#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
migrate_stock_cost.py - Migração para Pilar de Custos de Materiais

Adiciona campos necessários para rastreamento de custos de peças:
1. ItemLPU.valor_custo - Custo de aquisição da peça
2. StockMovement.chamado_id - Vínculo com chamado para rastreabilidade

Uso:
    python migrate_stock_cost.py [--check] [--apply]

Flags:
    --check  Apenas verifica se a migração é necessária
    --apply  Aplica a migração (padrão: modo seguro, só verifica)
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import create_app, db
from sqlalchemy import text, inspect

app = create_app()


def check_column_exists(table_name, column_name):
    """Verifica se uma coluna existe na tabela."""
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns


def run_migration(apply=False):
    """
    Executa a migração de forma segura.
    """
    print("\n" + "=" * 60)
    print("MIGRACAO: Pilar de Custos de Materiais")
    print("=" * 60)

    migrations_needed = []
    migrations_done = []

    with app.app_context():
        # 1. Verificar ItemLPU.valor_custo
        print("\n[1] Verificando ItemLPU.valor_custo...")
        if check_column_exists('itens_lpu', 'valor_custo'):
            print("    [OK] Coluna já existe.")
            migrations_done.append('itens_lpu.valor_custo')
        else:
            print("    [!] Coluna não existe - migração necessária.")
            migrations_needed.append({
                'table': 'itens_lpu',
                'column': 'valor_custo',
                'sql': "ALTER TABLE itens_lpu ADD COLUMN valor_custo FLOAT DEFAULT 0.0"
            })

        # 2. Verificar StockMovement.chamado_id
        print("\n[2] Verificando StockMovement.chamado_id...")
        if check_column_exists('stock_movements', 'chamado_id'):
            print("    [OK] Coluna já existe.")
            migrations_done.append('stock_movements.chamado_id')
        else:
            print("    [!] Coluna não existe - migração necessária.")
            migrations_needed.append({
                'table': 'stock_movements',
                'column': 'chamado_id',
                'sql': "ALTER TABLE stock_movements ADD COLUMN chamado_id INTEGER REFERENCES chamados(id)"
            })

        # Resumo
        print("\n" + "-" * 60)
        print("RESUMO")
        print("-" * 60)
        print(f"  Migrações já aplicadas: {len(migrations_done)}")
        print(f"  Migrações pendentes:    {len(migrations_needed)}")

        if not migrations_needed:
            print("\n  [OK] Banco de dados já está atualizado!")
            return True

        # Se não for aplicar, apenas mostra o que seria feito
        if not apply:
            print("\n  [INFO] Migrações que serão aplicadas:")
            for m in migrations_needed:
                print(f"    - {m['table']}.{m['column']}")
                print(f"      SQL: {m['sql']}")
            print("\n  Execute com --apply para aplicar as migrações.")
            return False

        # Aplicar migrações
        print("\n[*] Aplicando migrações...")
        for m in migrations_needed:
            try:
                print(f"    Executando: {m['table']}.{m['column']}...")
                db.session.execute(text(m['sql']))
                db.session.commit()
                print(f"    [OK] Coluna criada com sucesso.")
            except Exception as e:
                db.session.rollback()
                print(f"    [ERRO] Falha ao criar coluna: {e}")
                return False

        # Criar índice para chamado_id (performance)
        try:
            print("\n[3] Criando índice para stock_movements.chamado_id...")
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_stockmov_chamado ON stock_movements(chamado_id)"
            ))
            db.session.commit()
            print("    [OK] Índice criado.")
        except Exception as e:
            # Índice pode já existir em alguns bancos
            print(f"    [INFO] Índice: {e}")

        print("\n" + "=" * 60)
        print("[SUCESSO] Migração concluída!")
        print("=" * 60)
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migração de Custos de Materiais')
    parser.add_argument('--check', action='store_true', help='Apenas verifica status')
    parser.add_argument('--apply', action='store_true', help='Aplica as migrações')

    args = parser.parse_args()

    if args.check:
        run_migration(apply=False)
    elif args.apply:
        run_migration(apply=True)
    else:
        print("Uso: python migrate_stock_cost.py [--check | --apply]")
        print("  --check  Verifica se há migrações pendentes")
        print("  --apply  Aplica as migrações no banco")
