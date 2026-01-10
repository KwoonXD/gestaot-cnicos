#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
audit_custos.py - Auditoria de Integridade Financeira

Este script valida a migração do campo legado 'valor' para o novo 'custo_atribuido'
calculado pelo PricingService.

Objetivo:
- Identificar divergencias entre valor legado e custo calculado
- Quantificar o impacto financeiro da migracao
- Validar se o campo 'valor' pode ser abandonado com seguranca

Uso:
    python audit_custos.py [--fix] [--limit N] [--tecnico-id ID]

Opcoes:
    --fix         Atualiza custo_atribuido para chamados com valor None
    --limit N     Limita a analise aos primeiros N chamados
    --tecnico-id  Filtra por tecnico especifico
    --verbose     Mostra todos os chamados, nao apenas divergentes

Autor: Auditoria de Migracao 2025
"""

import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from decimal import Decimal

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configura a aplicacao Flask
from src import create_app, db
from src.models import Chamado, Tecnico
from src.services.pricing_service import (
    PricingService,
    ChamadoInput,
    ServicoConfig,
    HORAS_FRANQUIA_PADRAO
)


# ==============================================================================
# CONFIGURACAO
# ==============================================================================

DIVERGENCIA_THRESHOLD = 1.00  # R$ - divergencias acima desse valor sao reportadas
CURRENCY_SYMBOL = "R$"


# ==============================================================================
# FUNCOES AUXILIARES
# ==============================================================================

def format_currency(value):
    """Formata valor como moeda brasileira."""
    if value is None:
        return f"{CURRENCY_SYMBOL} --.--"
    return f"{CURRENCY_SYMBOL} {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_date(d):
    """Formata data para exibicao."""
    if d is None:
        return "----/--/--"
    return d.strftime("%d/%m/%Y")


def safe_float(value, default=0.0):
    """Converte valor para float de forma segura."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ==============================================================================
# AUDITORIA PRINCIPAL
# ==============================================================================

class CustoAuditor:
    """Auditor de custos para validacao da migracao."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.divergencias = []
        self.estatisticas = {
            'total_chamados': 0,
            'com_custo_atribuido': 0,
            'sem_custo_atribuido': 0,
            'com_valor_legado': 0,
            'divergentes': 0,
            'soma_valor_legado': 0.0,
            'soma_custo_atribuido': 0.0,
            'soma_custo_calculado': 0.0,
            'soma_divergencia_legado': 0.0,
            'soma_divergencia_atribuido': 0.0,
        }
        # Cache de contexto de lote por tecnico
        self._lote_cache = defaultdict(lambda: defaultdict(list))

    def _get_lote_key(self, chamado):
        """Gera chave de agrupamento por lote (data, cidade)."""
        city = chamado.cidade if chamado.cidade and chamado.cidade != 'Indefinido' else chamado.loja
        return (chamado.data_atendimento, city or "INDEFINIDO")

    def _build_lote_context(self, chamados):
        """
        Constroi contexto de lote para determinar qual chamado e o "primeiro" de cada lote.
        Retorna dict: chamado_id -> is_primeiro_lote
        """
        # Agrupa chamados por tecnico e lote
        lotes = defaultdict(lambda: defaultdict(list))

        for chamado in chamados:
            lote_key = self._get_lote_key(chamado)
            lotes[chamado.tecnico_id][lote_key].append(chamado)

        # Determina qual e o primeiro de cada lote
        primeiro_map = {}

        for tecnico_id, lotes_tecnico in lotes.items():
            for lote_key, chamados_lote in lotes_tecnico.items():
                # Ordena por ID para consistencia
                chamados_lote.sort(key=lambda c: c.id)

                # Marca primeiro do lote (apenas se paga_tecnico e nao pagamento_integral)
                ja_pagou_principal = False

                for chamado in chamados_lote:
                    servico = chamado.catalogo_servico
                    paga_tecnico = servico.paga_tecnico if servico else True
                    pagamento_integral = servico.pagamento_integral if servico else False

                    if pagamento_integral:
                        # Sempre paga cheio
                        primeiro_map[chamado.id] = True
                    elif not paga_tecnico:
                        # Nao paga, mantem estado
                        primeiro_map[chamado.id] = not ja_pagou_principal
                    else:
                        # Regra normal
                        if not ja_pagou_principal:
                            primeiro_map[chamado.id] = True
                            ja_pagou_principal = True
                        else:
                            primeiro_map[chamado.id] = False

        return primeiro_map

    def _calcular_custo_chamado(self, chamado, tecnico, is_primeiro_lote):
        """Calcula custo de um chamado usando PricingService."""
        config = PricingService.extract_servico_config(chamado.catalogo_servico, tecnico)

        chamado_input = ChamadoInput(
            id=chamado.id,
            data_atendimento=chamado.data_atendimento,
            cidade=chamado.cidade or chamado.loja or "INDEFINIDO",
            loja=chamado.loja,
            horas_trabalhadas=safe_float(chamado.horas_trabalhadas, HORAS_FRANQUIA_PADRAO),
            servico_config=config,
            fornecedor_peca=getattr(chamado, 'fornecedor_peca', None),
            custo_peca=safe_float(chamado.custo_peca, 0.0),
        )

        resultado = PricingService.calcular_custo_unitario(chamado_input, is_primeiro_lote)
        return resultado.custo_total

    def auditar(self, chamados, fix_missing=False):
        """
        Executa auditoria em lista de chamados.

        Args:
            chamados: Lista de objetos Chamado
            fix_missing: Se True, atualiza custo_atribuido para valores None

        Returns:
            dict com estatisticas da auditoria
        """
        if not chamados:
            print("\n[!] Nenhum chamado encontrado para auditar.")
            return self.estatisticas

        # Constroi contexto de lote
        print("\n[*] Construindo contexto de lotes...")
        primeiro_map = self._build_lote_context(chamados)

        # Cache de tecnicos
        tecnicos_cache = {}

        print(f"[*] Auditando {len(chamados)} chamados...\n")

        for chamado in chamados:
            self.estatisticas['total_chamados'] += 1

            # Busca tecnico (com cache)
            if chamado.tecnico_id not in tecnicos_cache:
                tecnicos_cache[chamado.tecnico_id] = chamado.tecnico or Tecnico.query.get(chamado.tecnico_id)
            tecnico = tecnicos_cache[chamado.tecnico_id]

            if not tecnico:
                if self.verbose:
                    print(f"  [!] Chamado {chamado.id}: Tecnico nao encontrado")
                continue

            # Determina se e primeiro do lote
            is_primeiro = primeiro_map.get(chamado.id, True)

            # Calcula custo
            custo_calculado = self._calcular_custo_chamado(chamado, tecnico, is_primeiro)

            # Extrai valores existentes
            valor_legado = safe_float(chamado.valor, 0.0)
            custo_atribuido = safe_float(chamado.custo_atribuido) if chamado.custo_atribuido is not None else None

            # Atualiza estatisticas
            self.estatisticas['soma_valor_legado'] += valor_legado
            self.estatisticas['soma_custo_calculado'] += custo_calculado

            if custo_atribuido is not None:
                self.estatisticas['com_custo_atribuido'] += 1
                self.estatisticas['soma_custo_atribuido'] += custo_atribuido
            else:
                self.estatisticas['sem_custo_atribuido'] += 1

            if valor_legado > 0:
                self.estatisticas['com_valor_legado'] += 1

            # Calcula divergencias
            divergencia_legado = custo_calculado - valor_legado
            divergencia_atribuido = 0.0

            if custo_atribuido is not None:
                divergencia_atribuido = custo_calculado - custo_atribuido
                self.estatisticas['soma_divergencia_atribuido'] += divergencia_atribuido

            self.estatisticas['soma_divergencia_legado'] += divergencia_legado

            # Verifica se divergencia e significativa
            is_divergente = abs(divergencia_legado) > DIVERGENCIA_THRESHOLD

            if is_divergente:
                self.estatisticas['divergentes'] += 1
                self.divergencias.append({
                    'id': chamado.id,
                    'id_chamado': chamado.id_chamado if hasattr(chamado, 'id_chamado') else f"#{chamado.id}",
                    'data': chamado.data_atendimento,
                    'tecnico': tecnico.nome[:20] if tecnico else "N/A",
                    'servico': chamado.servico_nome[:25] if hasattr(chamado, 'servico_nome') else "N/A",
                    'valor_legado': valor_legado,
                    'custo_atribuido': custo_atribuido,
                    'custo_calculado': custo_calculado,
                    'divergencia': divergencia_legado,
                    'is_primeiro_lote': is_primeiro,
                })

            # Fix missing custo_atribuido
            if fix_missing and custo_atribuido is None:
                chamado.custo_atribuido = custo_calculado
                if self.verbose:
                    print(f"  [FIX] Chamado {chamado.id}: custo_atribuido = {format_currency(custo_calculado)}")

        return self.estatisticas

    def print_report(self):
        """Imprime relatorio de auditoria."""
        stats = self.estatisticas

        # Header
        print("\n" + "=" * 100)
        print("RELATORIO DE AUDITORIA - MIGRACAO DE CUSTOS")
        print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print("=" * 100)

        # Estatisticas Gerais
        print("\n[ESTATISTICAS GERAIS]")
        print("-" * 50)
        print(f"  Total de Chamados Analisados: {stats['total_chamados']:,}")
        print(f"  Com custo_atribuido preenchido: {stats['com_custo_atribuido']:,}")
        print(f"  Sem custo_atribuido (NULL): {stats['sem_custo_atribuido']:,}")
        print(f"  Com valor legado > 0: {stats['com_valor_legado']:,}")
        print(f"  Divergencias > {format_currency(DIVERGENCIA_THRESHOLD)}: {stats['divergentes']:,}")

        # Somas Financeiras
        print("\n[TOTAIS FINANCEIROS]")
        print("-" * 50)
        print(f"  Soma Valor Legado (campo 'valor'):     {format_currency(stats['soma_valor_legado'])}")
        print(f"  Soma custo_atribuido (existentes):     {format_currency(stats['soma_custo_atribuido'])}")
        print(f"  Soma Custo Calculado (PricingService): {format_currency(stats['soma_custo_calculado'])}")

        # Impacto da Migracao
        print("\n[IMPACTO DA MIGRACAO]")
        print("-" * 50)

        diff_legado = stats['soma_custo_calculado'] - stats['soma_valor_legado']
        if diff_legado > 0:
            print(f"  vs Valor Legado: O novo calculo AUMENTARIA o custo em {format_currency(abs(diff_legado))}")
        elif diff_legado < 0:
            print(f"  vs Valor Legado: O novo calculo ECONOMIZARIA {format_currency(abs(diff_legado))}")
        else:
            print(f"  vs Valor Legado: Nenhuma diferenca financeira.")

        if stats['soma_custo_atribuido'] > 0:
            diff_atribuido = stats['soma_custo_calculado'] - stats['soma_custo_atribuido']
            if abs(diff_atribuido) > 1:
                if diff_atribuido > 0:
                    print(f"  vs custo_atribuido: Diferenca de +{format_currency(abs(diff_atribuido))}")
                else:
                    print(f"  vs custo_atribuido: Diferenca de -{format_currency(abs(diff_atribuido))}")
            else:
                print(f"  vs custo_atribuido: Valores consistentes (diff < R$ 1,00)")

        # Tabela de Divergencias
        if self.divergencias:
            print("\n[CHAMADOS COM DIVERGENCIA > {0}]".format(format_currency(DIVERGENCIA_THRESHOLD)))
            print("-" * 100)
            print(f"{'ID':<12} | {'Data':<10} | {'Tecnico':<20} | {'Legado':>12} | {'Calculado':>12} | {'Diff':>12} | {'Lote':<6}")
            print("-" * 100)

            # Ordena por divergencia (maior primeiro)
            divergencias_sorted = sorted(self.divergencias, key=lambda x: abs(x['divergencia']), reverse=True)

            # Limita a exibicao para nao poluir o console
            MAX_DISPLAY = 50
            for item in divergencias_sorted[:MAX_DISPLAY]:
                lote_flag = "1o" if item['is_primeiro_lote'] else "Adic"
                print(
                    f"{item['id_chamado']:<12} | "
                    f"{format_date(item['data']):<10} | "
                    f"{item['tecnico']:<20} | "
                    f"{format_currency(item['valor_legado']):>12} | "
                    f"{format_currency(item['custo_calculado']):>12} | "
                    f"{format_currency(item['divergencia']):>12} | "
                    f"{lote_flag:<6}"
                )

            if len(divergencias_sorted) > MAX_DISPLAY:
                print(f"\n  ... e mais {len(divergencias_sorted) - MAX_DISPLAY} chamados divergentes.")

        # Conclusao
        print("\n" + "=" * 100)
        print("[CONCLUSAO]")
        print("=" * 100)

        if stats['divergentes'] == 0:
            print("\n  ✅ MIGRACAO SEGURA: Nenhuma divergencia significativa encontrada.")
            print("     O campo 'valor' pode ser deprecado com seguranca.")
        elif stats['divergentes'] < stats['total_chamados'] * 0.01:  # Menos de 1%
            print(f"\n  ⚠️  ATENCAO: {stats['divergentes']} divergencias encontradas ({stats['divergentes']/stats['total_chamados']*100:.2f}%).")
            print("     Recomenda-se revisar os casos antes de deprecar o campo 'valor'.")
        else:
            print(f"\n  ❌ RISCO: {stats['divergentes']} divergencias encontradas ({stats['divergentes']/stats['total_chamados']*100:.2f}%).")
            print("     NAO e seguro deprecar o campo 'valor' sem correcao previa.")

        # Recomendacoes
        if stats['sem_custo_atribuido'] > 0:
            print(f"\n  [ACAO] {stats['sem_custo_atribuido']} chamados sem custo_atribuido.")
            print("         Execute com --fix para popular automaticamente.")

        print("\n")


# ==============================================================================
# MAIN
# ==============================================================================

def parse_args():
    """Parse argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Auditoria de custos - Validacao de migracao valor -> custo_atribuido"
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Atualiza custo_atribuido para chamados com valor NULL'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limita analise aos primeiros N chamados'
    )
    parser.add_argument(
        '--tecnico-id',
        type=int,
        default=None,
        help='Filtra por ID do tecnico'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Modo verboso - mostra mais detalhes'
    )
    parser.add_argument(
        '--only-pending',
        action='store_true',
        help='Audita apenas chamados nao pagos (pendentes de pagamento)'
    )
    return parser.parse_args()


def main():
    """Funcao principal."""
    args = parse_args()

    print("\n" + "=" * 60)
    print("AUDIT_CUSTOS.PY - Auditoria de Integridade Financeira")
    print("=" * 60)

    app = create_app()

    with app.app_context():
        # Monta query
        print("\n[*] Buscando chamados para auditoria...")

        query = Chamado.query.filter(
            Chamado.status_chamado == 'Concluído',
            Chamado.status_validacao == 'Aprovado'
        )

        if args.only_pending:
            query = query.filter(
                Chamado.pago == False,
                Chamado.pagamento_id == None
            )
            print("    Filtro: Apenas chamados pendentes de pagamento")

        if args.tecnico_id:
            query = query.filter(Chamado.tecnico_id == args.tecnico_id)
            print(f"    Filtro: Tecnico ID = {args.tecnico_id}")

        query = query.order_by(Chamado.data_atendimento.desc())

        if args.limit:
            query = query.limit(args.limit)
            print(f"    Limite: {args.limit} chamados")

        chamados = query.all()
        print(f"\n[*] {len(chamados)} chamados encontrados.\n")

        if not chamados:
            print("[!] Nenhum chamado atende aos criterios. Encerrando.")
            return

        # Executa auditoria
        auditor = CustoAuditor(verbose=args.verbose)
        auditor.auditar(chamados, fix_missing=args.fix)

        # Commit se --fix foi usado
        if args.fix:
            try:
                db.session.commit()
                print("\n[*] Alteracoes salvas no banco de dados.")
            except Exception as e:
                db.session.rollback()
                print(f"\n[!] Erro ao salvar: {e}")

        # Imprime relatorio
        auditor.print_report()


if __name__ == '__main__':
    main()
