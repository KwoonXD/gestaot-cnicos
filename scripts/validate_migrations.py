#!/usr/bin/env python3
"""
Script de validação de migrations para PostgreSQL.
Executa queries e retorna OK/WARN/FAIL.

Uso:
    python scripts/validate_migrations.py
    
Requer: psycopg2-binary (pip install psycopg2-binary)
"""

import os
import sys
from dataclasses import dataclass
from typing import List, Optional

try:
    import psycopg2
except ImportError:
    print("❌ FAIL: psycopg2 não instalado")
    print("   Execute: pip install psycopg2-binary")
    sys.exit(1)


@dataclass
class CheckResult:
    name: str
    status: str  # OK, WARN, FAIL
    message: str
    details: Optional[str] = None


def get_connection():
    """Obtém conexão com PostgreSQL."""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        return psycopg2.connect(database_url)
    
    return psycopg2.connect(
        host=os.environ.get('PGHOST', 'localhost'),
        port=os.environ.get('PGPORT', '5432'),
        database=os.environ.get('PGDATABASE', 'gestao'),
        user=os.environ.get('PGUSER', 'postgres'),
        password=os.environ.get('PGPASSWORD', '')
    )


def check_alembic_version(conn) -> CheckResult:
    """Verifica versão do Alembic."""
    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        
        if not row:
            return CheckResult("Alembic Version", "FAIL", "Nenhuma versão encontrada")
        
        version = row[0]
        if version == 'a004':
            return CheckResult("Alembic Version", "OK", f"Versão: {version}")
        else:
            return CheckResult("Alembic Version", "WARN", f"Versão: {version} (esperado: a004)")


def check_valor_nullable(conn) -> CheckResult:
    """Verifica se chamados.valor é nullable."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'chamados' AND column_name = 'valor'
        """)
        row = cur.fetchone()
    
    if row and row[0] == 'YES':
        return CheckResult("chamados.valor nullable", "OK", "Campo é nullable")
    else:
        return CheckResult("chamados.valor nullable", "FAIL", "Campo é NOT NULL (drift)")


def check_constraints(conn) -> CheckResult:
    """Verifica constraints de integridade."""
    expected = [
        'uq_tecnico_stock_tecnico_item',
        'ck_stock_movements_quantidade_positive',
        'ck_stock_movements_tipo_movimento',
        'ck_solicitacoes_reposicao_status',
        'ck_chamados_status_chamado',
        'ck_chamados_status_validacao'
    ]
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT conname FROM pg_constraint 
            WHERE conname = ANY(%s)
        """, (expected,))
        found = [row[0] for row in cur.fetchall()]
    
    missing = set(expected) - set(found)
    
    if not missing:
        return CheckResult("Constraints", "OK", f"{len(found)}/{len(expected)} presentes")
    else:
        return CheckResult("Constraints", "WARN", f"{len(found)}/{len(expected)}", 
                          f"Faltando: {', '.join(missing)}")


def check_duplicates(conn) -> CheckResult:
    """Verifica duplicidades em tecnico_stock."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT tecnico_id, item_lpu_id
                FROM tecnico_stock
                GROUP BY tecnico_id, item_lpu_id
                HAVING COUNT(*) > 1
            ) x
        """)
        count = cur.fetchone()[0]
    
    if count == 0:
        return CheckResult("Duplicidades tecnico_stock", "OK", "Sem duplicidades")
    else:
        return CheckResult("Duplicidades tecnico_stock", "FAIL", f"{count} duplicidades")


def check_invalid_quantities(conn) -> CheckResult:
    """Verifica quantidades inválidas."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM stock_movements
            WHERE quantidade IS NULL OR quantidade <= 0
        """)
        count = cur.fetchone()[0]
    
    if count == 0:
        return CheckResult("Quantidades stock_movements", "OK", "Todas válidas")
    else:
        return CheckResult("Quantidades stock_movements", "FAIL", f"{count} inválidas")


def check_monetary_types(conn) -> CheckResult:
    """Verifica se colunas monetárias são NUMERIC."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_name IN ('catalogo_servicos', 'itens_lpu', 'chamados')
            AND column_name IN ('valor_receita', 'valor_custo', 'custo_atribuido', 'valor')
            AND data_type = 'double precision'
        """)
        float_columns = cur.fetchall()
    
    if not float_columns:
        return CheckResult("Tipos monetários", "OK", "Todas NUMERIC")
    else:
        cols = [f"{r[0]}.{r[1]}" for r in float_columns]
        return CheckResult("Tipos monetários", "WARN", f"{len(float_columns)} FLOAT", ", ".join(cols))


def run_all_checks() -> List[CheckResult]:
    """Executa todas as verificações."""
    try:
        conn = get_connection()
    except Exception as e:
        return [CheckResult("Conexão", "FAIL", str(e))]
    
    results = []
    try:
        results.append(check_alembic_version(conn))
        results.append(check_valor_nullable(conn))
        results.append(check_constraints(conn))
        results.append(check_duplicates(conn))
        results.append(check_invalid_quantities(conn))
        results.append(check_monetary_types(conn))
    finally:
        conn.close()
    
    return results


def print_results(results: List[CheckResult]) -> int:
    """Imprime resultados formatados."""
    print("=" * 60)
    print("VALIDAÇÃO DE MIGRATIONS (PostgreSQL)")
    print("=" * 60)
    
    ok = warn = fail = 0
    
    for r in results:
        icon = {"OK": "✓", "WARN": "⚠", "FAIL": "✗"}.get(r.status, "?")
        print(f"{icon} [{r.status}] {r.name}: {r.message}")
        if r.details:
            print(f"    └─ {r.details}")
        
        if r.status == "OK": ok += 1
        elif r.status == "WARN": warn += 1
        else: fail += 1
    
    print("=" * 60)
    print(f"RESUMO: {ok} OK | {warn} WARN | {fail} FAIL")
    print("=" * 60)
    
    return fail


if __name__ == "__main__":
    fail_count = print_results(run_all_checks())
    sys.exit(1 if fail_count > 0 else 0)
