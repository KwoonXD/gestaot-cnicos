#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_migration.py - Verificacao de Integridade Pos-Migracao

Verifica se todos os chamados 'Concluido' possuem custo_atribuido preenchido.
Resultado esperado: 0 chamados com NULL.

Uso:
    python verify_migration.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import create_app, db
from src.models import Chamado

app = create_app()


def verify_migration():
    """
    Conta chamados concluidos com custo_atribuido NULL.
    Retorna True se nenhum for encontrado (migracao OK).
    """
    print("\n" + "=" * 60)
    print("VERIFY_MIGRATION.PY - Verificacao de Integridade")
    print("=" * 60)

    with app.app_context():
        # Conta chamados concluidos com custo_atribuido NULL
        null_count = Chamado.query.filter(
            Chamado.status_chamado == 'Finalizado',
            Chamado.custo_atribuido.is_(None)
        ).count()

        # Conta total de chamados concluidos
        total_concluidos = Chamado.query.filter(
            Chamado.status_chamado == 'Finalizado'
        ).count()

        # Conta chamados com custo preenchido
        com_custo = Chamado.query.filter(
            Chamado.status_chamado == 'Finalizado',
            Chamado.custo_atribuido.isnot(None)
        ).count()

        print(f"\n[RESULTADO]")
        print(f"  Total de chamados 'Concluido':        {total_concluidos}")
        print(f"  Com custo_atribuido preenchido:       {com_custo}")
        print(f"  Com custo_atribuido NULL:             {null_count}")

        print("\n" + "-" * 60)

        if null_count == 0:
            print("  [OK] Migracao validada com sucesso!")
            print("       Todos os chamados concluidos possuem custo_atribuido.")
            return True
        else:
            print(f"  [ERRO] {null_count} chamado(s) ainda sem custo_atribuido!")
            print("         Execute 'python audit_custos.py --fix' novamente.")

            # Lista os chamados problematicos (max 10)
            problematicos = Chamado.query.filter(
                Chamado.status_chamado == 'Finalizado',
                Chamado.custo_atribuido.is_(None)
            ).limit(10).all()

            if problematicos:
                print("\n  Chamados sem custo:")
                for c in problematicos:
                    print(f"    - {c.codigo_chamado} (ID: {c.id})")

            return False


if __name__ == '__main__':
    success = verify_migration()
    sys.exit(0 if success else 1)
