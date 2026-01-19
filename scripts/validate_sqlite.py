#!/usr/bin/env python3
"""
Validação de migrations para SQLite.
Executa queries de verificação no banco SQLite.

Uso:
    python scripts/validate_sqlite.py
"""

import os
import sqlite3
from pathlib import Path

# Encontrar o banco de dados
def find_database():
    """Procura o arquivo do banco SQLite."""
    possible_paths = [
        'instance/gestao.db',
        'gestao.db',
        '../instance/gestao.db',
    ]
    
    for p in possible_paths:
        if os.path.exists(p):
            return p
    
    return None


def run_validation():
    """Executa validações no banco SQLite."""
    db_path = find_database()
    
    if not db_path:
        print("❌ FAIL: Banco de dados não encontrado")
        print("   Procurado em: instance/gestao.db, gestao.db")
        return 1
    
    print("=" * 60)
    print("VALIDAÇÃO DE MIGRATIONS (SQLite)")
    print(f"Banco: {db_path}")
    print("=" * 60)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    ok = warn = fail = 0
    
    # 1. Verificar versão do Alembic
    print("\n📋 Verificando versão do Alembic...")
    try:
        cursor.execute("SELECT version_num FROM alembic_version")
        row = cursor.fetchone()
        if row and row[0] == 'a004':
            print(f"   ✓ [OK] Versão: {row[0]} (esperado)")
            ok += 1
        elif row:
            print(f"   ⚠ [WARN] Versão: {row[0]} (esperado: a004)")
            warn += 1
        else:
            print("   ✗ [FAIL] Nenhuma versão encontrada")
            fail += 1
    except sqlite3.OperationalError as e:
        print(f"   ✗ [FAIL] Erro: {e}")
        fail += 1
    
    # 2. Verificar tabelas existentes
    print("\n📋 Verificando tabelas principais...")
    tables = ['users', 'tecnicos', 'chamados', 'pagamentos', 'catalogo_servicos']
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = [r[0] for r in cursor.fetchall()]
    
    for t in tables:
        if t in existing:
            print(f"   ✓ [OK] Tabela '{t}' existe")
            ok += 1
        else:
            print(f"   ✗ [FAIL] Tabela '{t}' não encontrada")
            fail += 1
    
    # 3. Verificar duplicidades em tecnico_stock
    print("\n📋 Verificando duplicidades em tecnico_stock...")
    if 'tecnico_stock' in existing:
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT tecnico_id, item_lpu_id
                FROM tecnico_stock
                GROUP BY tecnico_id, item_lpu_id
                HAVING COUNT(*) > 1
            )
        """)
        count = cursor.fetchone()[0]
        if count == 0:
            print("   ✓ [OK] Sem duplicidades")
            ok += 1
        else:
            print(f"   ⚠ [WARN] {count} duplicidades encontradas")
            warn += 1
    else:
        print("   - [SKIP] Tabela tecnico_stock não existe")
    
    # 4. Verificar quantidades inválidas
    print("\n📋 Verificando quantidades em stock_movements...")
    if 'stock_movements' in existing:
        cursor.execute("""
            SELECT COUNT(*) FROM stock_movements
            WHERE quantidade IS NULL OR quantidade <= 0
        """)
        count = cursor.fetchone()[0]
        if count == 0:
            print("   ✓ [OK] Todas quantidades válidas")
            ok += 1
        else:
            print(f"   ✗ [FAIL] {count} quantidades inválidas")
            fail += 1
    else:
        print("   - [SKIP] Tabela stock_movements não existe")
    
    # 5. Verificar backfill de custo_atribuido
    print("\n📋 Verificando backfill (valor → custo_atribuido)...")
    if 'chamados' in existing:
        cursor.execute("""
            SELECT COUNT(*) FROM chamados
            WHERE valor IS NOT NULL AND valor > 0
            AND (custo_atribuido IS NULL OR custo_atribuido = 0)
        """)
        count = cursor.fetchone()[0]
        if count == 0:
            print("   ✓ [OK] Backfill completo")
            ok += 1
        else:
            print(f"   ⚠ [WARN] {count} registros sem backfill")
            warn += 1
    else:
        print("   - [SKIP] Tabela chamados não existe")
    
    # 6. Resumo de chamados
    print("\n📋 Resumo de chamados...")
    if 'chamados' in existing:
        cursor.execute("SELECT COUNT(*) FROM chamados")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chamados WHERE pago = 1")
        pagos = cursor.fetchone()[0]
        print(f"   ℹ Total: {total} | Pagos: {pagos} | Pendentes: {total - pagos}")
    
    # Resultado final
    print("\n" + "=" * 60)
    print(f"RESUMO: {ok} OK | {warn} WARN | {fail} FAIL")
    print("=" * 60)
    
    conn.close()
    
    return 1 if fail > 0 else 0


if __name__ == "__main__":
    import sys
    sys.exit(run_validation())
