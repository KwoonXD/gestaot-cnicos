"""
PricingService - Motor Unificado de Precificacao

Este servico centraliza TODA a logica de calculo de custos para tecnicos,
garantindo consistencia entre a criacao de chamados e o fechamento financeiro.

Regras de Negocio Implementadas:
1. Agrupamento por LOTE: (data_atendimento, cidade)
   - 1o chamado do lote: valor_custo_tecnico (cheio)
   - Demais chamados: valor_adicional_custo (reduzido)

2. Excecoes:
   - paga_tecnico=False (ex: Falha): R$ 0.00
   - pagamento_integral=True (ex: Retorno SPARE): sempre valor cheio

3. Horas Extras:
   - Se horas_trabalhadas > horas_franquia: cobra valor_hora_adicional_custo

4. Reembolso de Pecas:
   - Se fornecedor_peca='Tecnico': adiciona custo_peca ao valor

Autor: Refatoracao 2025
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from collections import defaultdict
from datetime import datetime


# ==============================================================================
# CONSTANTES DE NEGOCIO (Valores Default)
# ==============================================================================

HORAS_FRANQUIA_PADRAO = 2.0
VALOR_HORA_EXTRA_DEFAULT = 30.00
VALOR_ATENDIMENTO_BASE = 120.00
VALOR_ADICIONAL_LOJA = 20.00


# ==============================================================================
# DATA CLASSES (Contextos de Calculo)
# ==============================================================================

@dataclass
class ServicoConfig:
    """Configuracao do servico extraida do CatalogoServico ou defaults."""
    valor_custo_tecnico: float = VALOR_ATENDIMENTO_BASE
    valor_adicional_custo: float = VALOR_ADICIONAL_LOJA
    valor_hora_adicional_custo: float = VALOR_HORA_EXTRA_DEFAULT
    horas_franquia: float = HORAS_FRANQUIA_PADRAO
    paga_tecnico: bool = True
    pagamento_integral: bool = False

    # Receita (para criacao)
    valor_receita: float = 0.0
    valor_adicional_receita: float = 0.0
    valor_hora_adicional_receita: float = 0.0


@dataclass
class ChamadoInput:
    """
    Dados de entrada para calculo de custo de um chamado.
    Usado tanto na criacao quanto no fechamento.
    """
    id: Optional[int] = None  # ID do chamado (se existente)
    data_atendimento: Any = None  # date object
    cidade: str = "INDEFINIDO"
    loja: Optional[str] = None

    # Horas
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    horas_trabalhadas: float = HORAS_FRANQUIA_PADRAO

    # Servico
    servico_config: ServicoConfig = field(default_factory=ServicoConfig)

    # Peca
    fornecedor_peca: Optional[str] = None
    custo_peca: float = 0.0

    # Referencia ao objeto original (para update)
    _original: Any = None


@dataclass
class CustoCalculado:
    """Resultado do calculo de custo para um chamado."""
    custo_servico: float = 0.0
    custo_horas_extras: float = 0.0
    custo_peca: float = 0.0
    custo_total: float = 0.0

    # Flags
    is_adicional: bool = False
    is_primeiro_lote: bool = False
    horas_extras: float = 0.0

    # Receita (para criacao)
    receita_servico: float = 0.0
    receita_horas_extras: float = 0.0
    receita_total: float = 0.0


# ==============================================================================
# PRICING ENGINE (Motor de Calculo)
# ==============================================================================

class PricingService:
    """
    Motor unificado de precificacao.
    Garante que a mesma logica seja aplicada na criacao e no fechamento.
    """

    # --------------------------------------------------------------------------
    # METODOS AUXILIARES
    # --------------------------------------------------------------------------

    @staticmethod
    def calculate_hours_worked(hora_inicio: Optional[str], hora_fim: Optional[str]) -> float:
        """
        Calcula horas trabalhadas a partir de strings "HH:MM".
        Retorna float (ex: 2.5 para 2h30m).
        Tratamento: Se fim < inicio, assume virada de dia (+24h).
        """
        if not hora_inicio or not hora_fim:
            return HORAS_FRANQUIA_PADRAO

        try:
            from datetime import timedelta

            inicio = datetime.strptime(hora_inicio.strip(), '%H:%M')
            fim = datetime.strptime(hora_fim.strip(), '%H:%M')

            diff = fim - inicio

            if diff.total_seconds() < 0:
                diff = diff + timedelta(hours=24)

            horas = diff.total_seconds() / 3600
            return round(horas, 2)
        except Exception:
            return HORAS_FRANQUIA_PADRAO

    @staticmethod
    def extract_servico_config(catalogo_servico, tecnico=None) -> ServicoConfig:
        """
        Extrai configuracao de precificacao do CatalogoServico.
        Fallback para valores do Tecnico ou defaults se nao houver catalogo.
        """
        if catalogo_servico:
            return ServicoConfig(
                valor_custo_tecnico=float(catalogo_servico.valor_custo_tecnico or VALOR_ATENDIMENTO_BASE),
                valor_adicional_custo=float(catalogo_servico.valor_adicional_custo or VALOR_ADICIONAL_LOJA),
                valor_hora_adicional_custo=float(catalogo_servico.valor_hora_adicional_custo or VALOR_HORA_EXTRA_DEFAULT),
                horas_franquia=float(catalogo_servico.horas_franquia or HORAS_FRANQUIA_PADRAO),
                paga_tecnico=catalogo_servico.paga_tecnico if catalogo_servico.paga_tecnico is not None else True,
                pagamento_integral=catalogo_servico.pagamento_integral or False,
                # Receita
                valor_receita=float(catalogo_servico.valor_receita or 0.0),
                valor_adicional_receita=float(catalogo_servico.valor_adicional_receita or 0.0),
                valor_hora_adicional_receita=float(catalogo_servico.valor_hora_adicional_receita or 0.0),
            )

        # Fallback para valores do tecnico
        if tecnico:
            return ServicoConfig(
                valor_custo_tecnico=float(tecnico.valor_por_atendimento or VALOR_ATENDIMENTO_BASE),
                valor_adicional_custo=float(tecnico.valor_adicional_loja or VALOR_ADICIONAL_LOJA),
                valor_hora_adicional_custo=float(tecnico.valor_hora_adicional or VALOR_HORA_EXTRA_DEFAULT),
            )

        # Defaults globais
        return ServicoConfig()

    @staticmethod
    def get_lote_key(chamado_input: ChamadoInput) -> Tuple:
        """
        Gera a chave de agrupamento por lote.
        Chave: (data_atendimento, cidade)
        """
        city_key = chamado_input.cidade or chamado_input.loja or "INDEFINIDO"
        return (chamado_input.data_atendimento, city_key)

    # --------------------------------------------------------------------------
    # CALCULO INDIVIDUAL (Sem contexto de lote)
    # --------------------------------------------------------------------------

    @staticmethod
    def calcular_custo_unitario(
        chamado_input: ChamadoInput,
        is_primeiro_lote: bool = True
    ) -> CustoCalculado:
        """
        Calcula o custo de um UNICO chamado.

        Args:
            chamado_input: Dados do chamado
            is_primeiro_lote: Se True, usa valor cheio. Se False, usa valor adicional.

        Returns:
            CustoCalculado com todos os valores calculados.
        """
        config = chamado_input.servico_config
        resultado = CustoCalculado()

        # 1. Verificar se paga tecnico
        if not config.paga_tecnico:
            resultado.is_adicional = not is_primeiro_lote
            resultado.is_primeiro_lote = is_primeiro_lote
            return resultado  # Tudo zerado

        # 2. Calcular horas extras
        horas_trabalhadas = chamado_input.horas_trabalhadas
        horas_franquia = config.horas_franquia
        horas_extras = max(0.0, horas_trabalhadas - horas_franquia)

        resultado.horas_extras = horas_extras
        resultado.custo_horas_extras = horas_extras * config.valor_hora_adicional_custo
        resultado.receita_horas_extras = horas_extras * config.valor_hora_adicional_receita

        # 3. Determinar valor base (cheio vs adicional)
        if config.pagamento_integral:
            # Sempre valor cheio (ignora regra de lote)
            resultado.custo_servico = config.valor_custo_tecnico
            resultado.receita_servico = config.valor_receita
            resultado.is_primeiro_lote = True
            resultado.is_adicional = False
        else:
            if is_primeiro_lote:
                resultado.custo_servico = config.valor_custo_tecnico
                resultado.receita_servico = config.valor_receita
                resultado.is_primeiro_lote = True
                resultado.is_adicional = False
            else:
                resultado.custo_servico = config.valor_adicional_custo
                resultado.receita_servico = config.valor_adicional_receita
                resultado.is_primeiro_lote = False
                resultado.is_adicional = True

        # 4. Reembolso de peca
        if chamado_input.fornecedor_peca == 'Tecnico' and chamado_input.custo_peca:
            resultado.custo_peca = float(chamado_input.custo_peca)

        # 5. Totais
        resultado.custo_total = (
            resultado.custo_servico +
            resultado.custo_horas_extras +
            resultado.custo_peca
        )

        resultado.receita_total = (
            resultado.receita_servico +
            resultado.receita_horas_extras
        )

        return resultado

    # --------------------------------------------------------------------------
    # CALCULO EM LOTE (Com agrupamento por dia/cidade)
    # --------------------------------------------------------------------------

    @staticmethod
    def calcular_custos_lote(chamados_inputs: List[ChamadoInput]) -> Dict[Any, CustoCalculado]:
        """
        Calcula custos para uma lista de chamados aplicando regras de LOTE.

        Regra de Lote:
        - Agrupa por (data_atendimento, cidade)
        - 1o chamado de cada grupo: valor cheio
        - Demais: valor adicional
        - Excecao: pagamento_integral=True sempre paga cheio

        Args:
            chamados_inputs: Lista de ChamadoInput

        Returns:
            Dict mapeando ID/indice do chamado para CustoCalculado
        """
        resultados = {}

        # 1. Agrupar por lote
        grupos = defaultdict(list)
        for idx, chamado in enumerate(chamados_inputs):
            key = PricingService.get_lote_key(chamado)
            grupos[key].append((idx, chamado))

        # 2. Processar cada grupo
        for lote_key, chamados_grupo in grupos.items():
            ja_pagou_principal = False

            # Ordenar por ID (se existir) para consistencia
            chamados_grupo.sort(key=lambda x: (x[1].id or 0, x[0]))

            for idx, chamado in chamados_grupo:
                config = chamado.servico_config

                # Determinar se e primeiro do lote
                if config.pagamento_integral:
                    # Sempre paga cheio, nao consome slot de "principal"
                    is_primeiro = True
                elif not config.paga_tecnico:
                    # Nao paga, nao consome slot
                    is_primeiro = not ja_pagou_principal
                else:
                    # Regra normal de lote
                    if not ja_pagou_principal:
                        is_primeiro = True
                        ja_pagou_principal = True
                    else:
                        is_primeiro = False

                # Calcular custo
                resultado = PricingService.calcular_custo_unitario(chamado, is_primeiro)

                # Usar ID do chamado se existir, senao indice
                key = chamado.id if chamado.id else idx
                resultados[key] = resultado

        return resultados

    # --------------------------------------------------------------------------
    # METODOS DE INTEGRACAO (Para uso nos Services)
    # --------------------------------------------------------------------------

    @classmethod
    def processar_criacao_multipla(
        cls,
        fsas: List[Dict],
        logistica: Dict,
        services_map: Dict
    ) -> List[Dict]:
        """
        Processa criacao de multiplos chamados retornando valores calculados.
        Usado pelo ChamadoService.create_multiplo.

        Args:
            fsas: Lista de dicts com dados dos FSAs
            logistica: Dict com tecnico_id, data_atendimento, cidade
            services_map: Dict mapeando catalogo_servico_id -> CatalogoServico

        Returns:
            Lista de dicts com valores calculados para cada FSA
        """
        from datetime import datetime as dt

        # Parse data
        try:
            data_atendimento = dt.strptime(logistica['data_atendimento'], '%Y-%m-%d').date()
        except (ValueError, KeyError):
            data_atendimento = dt.now().date()

        cidade = logistica.get('cidade', 'INDEFINIDO')

        # Preparar inputs
        chamados_inputs = []
        for idx, fsa in enumerate(fsas):
            # Extrair servico
            servico_id = fsa.get('catalogo_servico_id')
            try:
                servico_id = int(servico_id) if servico_id else None
            except (ValueError, TypeError):
                servico_id = None

            servico = services_map.get(servico_id) if servico_id else None
            config = cls.extract_servico_config(servico)

            # Calcular horas
            horas = cls.calculate_hours_worked(
                fsa.get('hora_inicio'),
                fsa.get('hora_fim')
            )

            chamado_input = ChamadoInput(
                id=idx,  # Usar indice como ID temporario
                data_atendimento=data_atendimento,
                cidade=cidade,
                hora_inicio=fsa.get('hora_inicio'),
                hora_fim=fsa.get('hora_fim'),
                horas_trabalhadas=horas,
                servico_config=config,
                fornecedor_peca=fsa.get('fornecedor_peca'),
                custo_peca=float(fsa.get('custo_peca', 0) or 0),
                _original=fsa
            )
            chamados_inputs.append(chamado_input)

        # Ordenar por valor receita (maior primeiro para garantir que mais caro pague cheio)
        chamados_inputs.sort(key=lambda x: x.servico_config.valor_receita, reverse=True)

        # Recalcular IDs apos ordenacao
        for new_idx, ci in enumerate(chamados_inputs):
            ci.id = new_idx

        # Calcular custos
        resultados = cls.calcular_custos_lote(chamados_inputs)

        # Preparar saida
        output = []
        for chamado_input in chamados_inputs:
            resultado = resultados[chamado_input.id]
            output.append({
                'fsa': chamado_input._original,
                'horas_trabalhadas': chamado_input.horas_trabalhadas,
                'custo_atribuido': resultado.custo_total,
                'valor_receita_servico': resultado.receita_servico + resultado.receita_horas_extras,
                'valor_receita_total': resultado.receita_total,
                'is_adicional': resultado.is_adicional,
                'horas_extras': resultado.horas_extras,
                'custo_horas_extras': resultado.custo_horas_extras,
            })

        return output

    @classmethod
    def processar_fechamento(cls, chamados, tecnico) -> float:
        """
        Processa custos de chamados no fechamento (Pagamento).
        Atualiza custo_atribuido de cada chamado e retorna total.
        Usado pelo FinanceiroService.

        Args:
            chamados: Lista de objetos Chamado (ORM)
            tecnico: Objeto Tecnico (ORM) - para fallback de valores

        Returns:
            float: Total a pagar
        """
        if not chamados:
            return 0.0

        # Preparar inputs
        chamados_inputs = []
        for chamado in chamados:
            config = cls.extract_servico_config(chamado.catalogo_servico, tecnico)

            # Obter horas trabalhadas (ja calculado ou default)
            horas = float(chamado.horas_trabalhadas or HORAS_FRANQUIA_PADRAO)

            chamado_input = ChamadoInput(
                id=chamado.id,
                data_atendimento=chamado.data_atendimento,
                cidade=getattr(chamado, 'cidade', None) or chamado.loja or "INDEFINIDO",
                loja=chamado.loja,
                horas_trabalhadas=horas,
                servico_config=config,
                fornecedor_peca=getattr(chamado, 'fornecedor_peca', None),
                custo_peca=float(chamado.custo_peca or 0),
                _original=chamado
            )
            chamados_inputs.append(chamado_input)

        # Calcular custos
        resultados = cls.calcular_custos_lote(chamados_inputs)

        # Atualizar chamados e calcular total
        total = 0.0
        for chamado in chamados:
            resultado = resultados.get(chamado.id)
            if resultado:
                chamado.custo_atribuido = resultado.custo_total
                total += resultado.custo_total

        return total

    @classmethod
    def calcular_custo_tempo_real(cls, chamado, tecnico) -> float:
        """
        Calcula custo de um chamado em tempo real (na aprovacao).
        Considera outros chamados do mesmo dia/cidade ja aprovados.
        Usado pelo FinanceiroService.registrar_credito_servico.

        Args:
            chamado: Objeto Chamado sendo aprovado
            tecnico: Objeto Tecnico

        Returns:
            float: Custo calculado
        """
        # Import local para evitar circular dependency
        from src.models import Chamado as ChamadoModel

        config = cls.extract_servico_config(chamado.catalogo_servico, tecnico)

        # Verificar se ja existe outro chamado aprovado no mesmo lote
        city_key = chamado.cidade if chamado.cidade and chamado.cidade != 'Indefinido' else chamado.loja

        outros_chamados = ChamadoModel.query.filter(
            ChamadoModel.tecnico_id == chamado.tecnico_id,
            ChamadoModel.data_atendimento == chamado.data_atendimento,
            ChamadoModel.status_chamado == 'Concluído',
            ChamadoModel.status_validacao == 'Aprovado',
            ChamadoModel.id != chamado.id
        ).all()

        # Filtrar por cidade/loja
        outros_no_lote = [
            c for c in outros_chamados
            if (getattr(c, 'cidade', '') == chamado.cidade or getattr(c, 'loja', '') == chamado.loja)
        ]

        is_primeiro = len(outros_no_lote) == 0

        # Calcular
        chamado_input = ChamadoInput(
            id=chamado.id,
            data_atendimento=chamado.data_atendimento,
            cidade=chamado.cidade or chamado.loja or "INDEFINIDO",
            horas_trabalhadas=float(chamado.horas_trabalhadas or HORAS_FRANQUIA_PADRAO),
            servico_config=config,
            fornecedor_peca=getattr(chamado, 'fornecedor_peca', None),
            custo_peca=float(chamado.custo_peca or 0),
        )

        resultado = cls.calcular_custo_unitario(chamado_input, is_primeiro)
        return resultado.custo_total

    # --------------------------------------------------------------------------
    # PRECOS POR CONTRATO (Tabela de Precos Personalizada)
    # --------------------------------------------------------------------------

    @staticmethod
    def get_valor_peca(contrato_id: int, item_lpu_id: int) -> float:
        """
        Retorna o valor de venda de uma peca para um contrato especifico.
        Interface simplificada que retorna apenas o valor float.

        REGRA DE NEGOCIO (Simplificada):
        - O preco de venda vem EXCLUSIVAMENTE da tabela ContratoItem.
        - Se nao houver ContratoItem, retorna 0.0 (item nao precificado).
        - O catalogo ItemLPU serve apenas para definicao do produto (Nome/SKU).

        Args:
            contrato_id: ID do cliente/contrato
            item_lpu_id: ID do ItemLPU (peca)

        Returns:
            float: Valor de venda da peca (0.0 se nao precificado no contrato)
        """
        from src.models import ContratoItem

        # Buscar preco EXCLUSIVAMENTE no contrato
        contrato_item = ContratoItem.query.filter_by(
            cliente_id=contrato_id,
            item_lpu_id=item_lpu_id,
            ativo=True
        ).first()

        if contrato_item:
            return float(contrato_item.valor_venda or 0.0)

        # SEM FALLBACK: Item nao precificado neste contrato
        return 0.0

    @staticmethod
    def get_valor_peca_contrato(cliente_id: int, item_id: int) -> dict:
        """
        Busca o valor de venda de uma peca para um cliente especifico.

        REGRA DE NEGOCIO (Simplificada):
        - O preco de venda vem EXCLUSIVAMENTE da tabela ContratoItem.
        - Se nao houver ContratoItem, retorna is_precificado=False.
        - O valor_custo (almoxarifado) serve apenas para referencia de margem.

        Args:
            cliente_id: ID do cliente/contrato
            item_id: ID do ItemLPU (peca)

        Returns:
            dict: {
                'valor_venda': float,
                'valor_repasse': float or None,
                'valor_custo': float (referencia),
                'is_precificado': bool,
                'margem': float
            }
        """
        from src.models import ContratoItem, ItemLPU

        # Buscar preco EXCLUSIVAMENTE no contrato
        contrato_item = ContratoItem.query.filter_by(
            cliente_id=cliente_id,
            item_lpu_id=item_id,
            ativo=True
        ).first()

        if contrato_item:
            return {
                'valor_venda': contrato_item.valor_venda,
                'valor_repasse': contrato_item.valor_repasse,
                'valor_custo': contrato_item.item_lpu.valor_custo if contrato_item.item_lpu else 0,
                'is_precificado': True,
                'margem': contrato_item.margem
            }

        # SEM FALLBACK: Buscar apenas custo de referencia
        item = ItemLPU.query.get(item_id)
        return {
            'valor_venda': 0.0,
            'valor_repasse': None,
            'valor_custo': float(item.valor_custo or 0) if item else 0.0,
            'is_precificado': False,
            'margem': 0.0
        }

    @staticmethod
    def get_tabela_precos_contrato(cliente_id: int) -> list:
        """
        Retorna a tabela de precos para um cliente.

        REGRA DE NEGOCIO (Simplificada):
        - Retorna APENAS itens que possuem preco definido no contrato.
        - Itens sem ContratoItem NAO sao cobraveis neste contrato.

        Args:
            cliente_id: ID do cliente/contrato

        Returns:
            Lista de dicts com itens precificados para este cliente.
        """
        from src.models import ContratoItem

        resultado = []

        # Buscar APENAS itens precificados neste contrato
        contrato_itens = ContratoItem.query.filter_by(
            cliente_id=cliente_id,
            ativo=True
        ).all()

        for ci in contrato_itens:
            item = ci.item_lpu
            if not item:
                continue

            resultado.append({
                'item_id': item.id,
                'nome': item.nome,
                'valor_venda': ci.valor_venda,
                'valor_repasse': ci.valor_repasse,
                'valor_custo': float(item.valor_custo or 0),
                'margem': ci.margem,
                'margem_percent': round(ci.margem_percent, 1)
            })

        return resultado
