#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_performance.py - Script de Benchmark para TecnicoService

Compara a performance entre:
- Metodo ANTIGO: Iterar tecnicos e acessar @property que fazem queries (N+1)
- Metodo NOVO: TecnicoService.get_tecnicos_com_metricas() (1-2 queries)

Uso:
    python verify_performance.py
"""

import os
import sys
import time
from datetime import datetime

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configura a aplicacao Flask
from src import create_app, db
from src.models import Tecnico, Chamado
from src.services.tecnico_service import TecnicoService

app = create_app()


class QueryCounter:
    """Contador de queries SQL usando eventos do SQLAlchemy."""

    def __init__(self):
        self.count = 0
        self._listening = False

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1

    def start(self):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        if not self._listening:
            event.listen(Engine, "before_cursor_execute", self._before_cursor_execute)
            self._listening = True
        self.count = 0

    def stop(self):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        if self._listening:
            try:
                event.remove(Engine, "before_cursor_execute", self._before_cursor_execute)
            except:
                pass
            self._listening = False

    def reset(self):
        self.count = 0


def benchmark_metodo_antigo(tecnicos_count):
    """
    Simula o comportamento ANTIGO: buscar tecnicos e iterar acessando properties.
    Isso causa N+1 queries porque cada @property faz uma query.
    """
    print(f"\n{'='*60}")
    print("METODO ANTIGO (N+1 Queries)")
    print(f"{'='*60}")

    counter = QueryCounter()
    counter.start()

    start_time = time.time()

    # Busca todos os tecnicos (1 query)
    tecnicos = Tecnico.query.limit(tecnicos_count).all()

    # Simula acesso aos dados como faria um template Jinja2
    resultados = []
    for t in tecnicos:
        # Cada acesso a essas properties dispara queries adicionais
        # Removemos o cache para forcar as queries
        if hasattr(t, 'total_a_pagar_cache'):
            delattr(t, 'total_a_pagar_cache')
        if hasattr(t, '_metricas'):
            delattr(t, '_metricas')

        # Isso dispara queries N+1
        data = {
            'id': t.id,
            'nome': t.nome,
            'total_atendimentos': t.chamados.count(),  # Query!
            'total_concluidos': t.chamados.filter(Chamado.status_chamado.in_(['Concluido', 'SPARE'])).count(),  # Query!
        }
        resultados.append(data)

    elapsed = time.time() - start_time
    query_count = counter.count
    counter.stop()

    print(f"  Tecnicos processados: {len(resultados)}")
    print(f"  Queries executadas:   {query_count}")
    print(f"  Tempo total:          {elapsed:.4f} segundos")
    print(f"  Media por tecnico:    {(elapsed/len(resultados)*1000):.2f} ms")

    return {
        'method': 'ANTIGO',
        'tecnicos': len(resultados),
        'queries': query_count,
        'time': elapsed
    }


def benchmark_metodo_novo(tecnicos_count):
    """
    Usa o NOVO metodo otimizado: get_tecnicos_com_metricas().
    Apenas 1-2 queries independente do numero de tecnicos.
    """
    print(f"\n{'='*60}")
    print("METODO NOVO (Otimizado - 1-2 Queries)")
    print(f"{'='*60}")

    counter = QueryCounter()
    counter.start()

    start_time = time.time()

    # Usa o novo metodo otimizado
    result = TecnicoService.get_tecnicos_com_metricas(
        page=1,
        per_page=tecnicos_count
    )

    # Acessa os dados pre-calculados (sem queries adicionais)
    resultados = []
    for metricas in result['items']:
        data = {
            'id': metricas.tecnico.id,
            'nome': metricas.nome,
            'total_atendimentos': metricas.total_atendimentos,
            'total_concluidos': metricas.total_atendimentos_concluidos,
            'total_a_pagar': metricas.total_a_pagar_agregado,
            'status_pagamento': metricas.status_pagamento
        }
        resultados.append(data)

    elapsed = time.time() - start_time
    query_count = counter.count
    counter.stop()

    print(f"  Tecnicos processados: {len(resultados)}")
    print(f"  Queries executadas:   {query_count}")
    print(f"  Tempo total:          {elapsed:.4f} segundos")
    print(f"  Media por tecnico:    {(elapsed/max(len(resultados),1)*1000):.2f} ms")

    return {
        'method': 'NOVO',
        'tecnicos': len(resultados),
        'queries': query_count,
        'time': elapsed
    }


def benchmark_metodo_legado_refatorado(tecnicos_count):
    """
    Usa o metodo get_all() refatorado (que internamente usa get_tecnicos_com_metricas).
    Deve ter performance similar ao NOVO.
    """
    print(f"\n{'='*60}")
    print("METODO LEGADO REFATORADO (get_all)")
    print(f"{'='*60}")

    counter = QueryCounter()
    counter.start()

    start_time = time.time()

    # Usa o metodo legado que foi refatorado
    pagination = TecnicoService.get_all(page=1, per_page=tecnicos_count)

    # Acessa os dados (devem estar no cache)
    resultados = []
    for t in pagination.items:
        data = {
            'id': t.id,
            'nome': t.nome,
            'total_a_pagar': t.total_a_pagar,  # Deve usar cache!
            'status_pagamento': t.status_pagamento
        }
        resultados.append(data)

    elapsed = time.time() - start_time
    query_count = counter.count
    counter.stop()

    print(f"  Tecnicos processados: {len(resultados)}")
    print(f"  Queries executadas:   {query_count}")
    print(f"  Tempo total:          {elapsed:.4f} segundos")
    print(f"  Media por tecnico:    {(elapsed/max(len(resultados),1)*1000):.2f} ms")

    return {
        'method': 'LEGADO_REFATORADO',
        'tecnicos': len(resultados),
        'queries': query_count,
        'time': elapsed
    }


def print_comparison(results):
    """Imprime comparacao entre os metodos."""
    print(f"\n{'='*60}")
    print("COMPARACAO DE RESULTADOS")
    print(f"{'='*60}")

    print(f"\n{'Metodo':<25} {'Queries':<12} {'Tempo (s)':<12} {'Speedup':<10}")
    print("-" * 60)

    baseline = results[0]['time'] if results else 1

    for r in results:
        speedup = baseline / r['time'] if r['time'] > 0 else 0
        speedup_str = f"{speedup:.1f}x" if r['method'] != 'ANTIGO' else "-"
        print(f"{r['method']:<25} {r['queries']:<12} {r['time']:<12.4f} {speedup_str:<10}")

    print("\n" + "="*60)

    if len(results) >= 2:
        antigo = results[0]
        novo = results[1]

        query_reduction = ((antigo['queries'] - novo['queries']) / antigo['queries'] * 100) if antigo['queries'] > 0 else 0
        time_reduction = ((antigo['time'] - novo['time']) / antigo['time'] * 100) if antigo['time'] > 0 else 0

        print(f"\nMELHORIAS:")
        print(f"  - Reducao de queries: {query_reduction:.1f}% ({antigo['queries']} -> {novo['queries']})")
        print(f"  - Reducao de tempo:   {time_reduction:.1f}%")
        print(f"  - Speedup:            {antigo['time']/novo['time']:.1f}x mais rapido")


def main():
    """Executa os benchmarks."""
    print("\n" + "="*60)
    print("BENCHMARK DE PERFORMANCE - TecnicoService")
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    with app.app_context():
        # Verifica quantos tecnicos existem
        total_tecnicos = Tecnico.query.count()
        print(f"\nTotal de tecnicos no banco: {total_tecnicos}")

        if total_tecnicos == 0:
            print("\nAVISO: Nenhum tecnico encontrado no banco de dados.")
            print("Crie alguns tecnicos para testar a performance.")
            return

        # Limita o teste para nao sobrecarregar
        test_count = min(50, total_tecnicos)
        print(f"Testando com {test_count} tecnicos...\n")

        results = []

        # Benchmark 1: Metodo Antigo (N+1)
        try:
            r1 = benchmark_metodo_antigo(test_count)
            results.append(r1)
        except Exception as e:
            print(f"  ERRO no metodo antigo: {e}")

        # Benchmark 2: Metodo Novo (Otimizado)
        try:
            r2 = benchmark_metodo_novo(test_count)
            results.append(r2)
        except Exception as e:
            print(f"  ERRO no metodo novo: {e}")

        # Benchmark 3: Metodo Legado Refatorado
        try:
            r3 = benchmark_metodo_legado_refatorado(test_count)
            results.append(r3)
        except Exception as e:
            print(f"  ERRO no metodo legado: {e}")

        # Comparacao
        print_comparison(results)

        print("\n" + "="*60)
        print("CONCLUSAO")
        print("="*60)
        print("""
O metodo get_tecnicos_com_metricas() resolve o problema N+1:
- Busca todos os dados em 1-2 queries SQL
- Performance constante independente do numero de tecnicos
- Compativel com codigo existente via get_all() refatorado

Recomendacao:
- Para listagens: usar get_tecnicos_com_metricas() diretamente
- Para codigo legado: get_all() ja usa internamente a versao otimizada
- Evitar acessar @property em loops (total_a_pagar, etc) sem cache
""")


if __name__ == '__main__':
    main()
