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
from decimal import Decimal, ROUND_HALF_UP


# ==============================================================================
# CONSTANTES DE NEGOCIO (Valores Default)
# ==============================================================================

HORAS_FRANQUIA_PADRAO = Decimal('2.0')
VALOR_HORA_EXTRA_DEFAULT = Decimal('30.00')
VALOR_ATENDIMENTO_BASE = Decimal('120.00')
VALOR_ADICIONAL_LOJA = Decimal('20.00')


# ==============================================================================
# DATA CLASSES (Contextos de Calculo)
# ==============================================================================

@dataclass
class ServicoConfig:
    """Configuracao do servico extraida do CatalogoServico ou defaults."""
    valor_custo_tecnico: Decimal = VALOR_ATENDIMENTO_BASE
    valor_adicional_custo: Decimal = VALOR_ADICIONAL_LOJA
    valor_hora_adicional_custo: Decimal = VALOR_HORA_EXTRA_DEFAULT
    horas_franquia: Decimal = HORAS_FRANQUIA_PADRAO
    paga_tecnico: bool = True
    pagamento_integral: bool = False

    # Receita (para criacao)
    valor_receita: Decimal = Decimal('0.00')
    valor_adicional_receita: Decimal = Decimal('0.00')
    valor_hora_adicional_receita: Decimal = Decimal('0.00')


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
    horas_trabalhadas: Decimal = HORAS_FRANQUIA_PADRAO

    # Servico
    servico_config: ServicoConfig = field(default_factory=ServicoConfig)

    # Peca
    fornecedor_peca: Optional[str] = None
    custo_peca: Decimal = Decimal('0.00')

    # Referencia ao objeto original (para update)
    _original: Any = None


@dataclass
class CustoCalculado:
    """Resultado do calculo de custo para um chamado."""
    custo_servico: Decimal = Decimal('0.00')
    custo_horas_extras: Decimal = Decimal('0.00')
    custo_peca: Decimal = Decimal('0.00')
    custo_total: Decimal = Decimal('0.00')

    # Flags
    is_adicional: bool = False
    is_primeiro_lote: bool = False
    horas_extras: Decimal = Decimal('0.00')

    # Receita (para criacao)
    receita_servico: Decimal = Decimal('0.00')
    receita_horas_extras: Decimal = Decimal('0.00')
    receita_total: Decimal = Decimal('0.00')


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
    def _to_decimal(value, default=Decimal('0.00')):
        if value is None:
            return default
        return Decimal(str(value))

    @staticmethod
    def calculate_hours_worked(hora_inicio: Optional[str], hora_fim: Optional[str]) -> Decimal:
        """
        Calcula horas trabalhadas a partir de strings "HH:MM".
        Retorna Decimal (ex: 2.5 para 2h30m).
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
            return Decimal(str(horas)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return HORAS_FRANQUIA_PADRAO

    @staticmethod
    def extract_servico_config(catalogo_servico, tecnico=None) -> ServicoConfig:
        """
        Extrai configuracao de precificacao do CatalogoServico.
        Fallback para valores do Tecnico ou defaults se nao houver catalogo.
        """
        td = PricingService._to_decimal
        
        if catalogo_servico:
            return ServicoConfig(
                valor_custo_tecnico=td(catalogo_servico.valor_custo_tecnico, VALOR_ATENDIMENTO_BASE),
                valor_adicional_custo=td(catalogo_servico.valor_adicional_custo, VALOR_ADICIONAL_LOJA),
                valor_hora_adicional_custo=td(catalogo_servico.valor_hora_adicional_custo, VALOR_HORA_EXTRA_DEFAULT),
                horas_franquia=td(catalogo_servico.horas_franquia, HORAS_FRANQUIA_PADRAO),
                paga_tecnico=catalogo_servico.paga_tecnico if catalogo_servico.paga_tecnico is not None else True,
                pagamento_integral=catalogo_servico.pagamento_integral or False,
                # Receita
                valor_receita=td(catalogo_servico.valor_receita),
                valor_adicional_receita=td(catalogo_servico.valor_adicional_receita),
                valor_hora_adicional_receita=td(catalogo_servico.valor_hora_adicional_receita),
            )

        # Fallback para valores do tecnico
        if tecnico:
            return ServicoConfig(
                valor_custo_tecnico=td(tecnico.valor_por_atendimento, VALOR_ATENDIMENTO_BASE),
                valor_adicional_custo=td(tecnico.valor_adicional_loja, VALOR_ADICIONAL_LOJA),
                valor_hora_adicional_custo=td(tecnico.valor_hora_adicional, VALOR_HORA_EXTRA_DEFAULT),
            )

        # Defaults globais
        return ServicoConfig()

    @staticmethod
    def get_lote_key(chamado_input: ChamadoInput) -> Tuple:
        """
        Gera a chave de agrupamento por lote.
        Chave: (data_atendimento, cidade_normalizada)
        """
        from src.utils.domain import normalize_city
        
        city_raw = chamado_input.cidade or chamado_input.loja
        city_key = normalize_city(city_raw)
        
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
        horas_extras = max(Decimal('0.00'), horas_trabalhadas - horas_franquia)

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
            resultado.custo_peca = chamado_input.custo_peca

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

        # Arredondar finais
        resultado.custo_total = resultado.custo_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        resultado.receita_total = resultado.receita_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return resultado

    # --------------------------------------------------------------------------
    # CALCULO EM LOTE (Com agrupamento por dia/cidade)
    # --------------------------------------------------------------------------

    @staticmethod
    def calcular_custos_lote(chamados_inputs: List[ChamadoInput]) -> Dict[Any, CustoCalculado]:
        """
        Calcula custos para uma lista de chamados aplicando regras de LOTE.
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
        """
        from datetime import datetime as dt
        td = cls._to_decimal

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
                custo_peca=td(fsa.get('custo_peca')),
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
    def processar_fechamento(cls, chamados, tecnico) -> Decimal:
        """
        Processa custos de chamados no fechamento (Pagamento).
        Atualiza custo_atribuido de cada chamado e retorna total.
        Retorna Decimal.
        """
        if not chamados:
            return Decimal('0.00')

        td = cls._to_decimal

        # Preparar inputs
        chamados_inputs = []
        for chamado in chamados:
            config = cls.extract_servico_config(chamado.catalogo_servico, tecnico)

            # Obter horas trabalhadas (ja calculado ou default)
            horas = td(chamado.horas_trabalhadas, HORAS_FRANQUIA_PADRAO)

            chamado_input = ChamadoInput(
                id=chamado.id,
                data_atendimento=chamado.data_atendimento,
                cidade=getattr(chamado, 'cidade', None) or chamado.loja or "INDEFINIDO",
                loja=chamado.loja,
                horas_trabalhadas=horas,
                servico_config=config,
                fornecedor_peca=getattr(chamado, 'fornecedor_peca', None),
                custo_peca=td(chamado.custo_peca),
                _original=chamado
            )
            chamados_inputs.append(chamado_input)

        # Calcular custos
        resultados = cls.calcular_custos_lote(chamados_inputs)

        # Atualizar chamados e calcular total
        total = Decimal('0.00')
        for chamado in chamados:
            resultado = resultados.get(chamado.id)
            if resultado:
                chamado.custo_atribuido = resultado.custo_total
                total += resultado.custo_total

        return total

    @classmethod
    def calcular_custo_tempo_real(cls, chamado, tecnico) -> Decimal:
        """
        Calcula custo de um chamado em tempo real (na aprovacao).
        Retorna Decimal.
        """
        # Import local para evitar circular dependency
        from src.models import Chamado as ChamadoModel

        td = cls._to_decimal

        # 1. Preparar Input do Chamado Atual
        chamado_input_atual = ChamadoInput(
            id=chamado.id or -1, # ID -1 se ainda nao persistido (transitorio)
            data_atendimento=chamado.data_atendimento,
            cidade=chamado.cidade or chamado.loja or "INDEFINIDO",
            loja=chamado.loja,
            horas_trabalhadas=td(chamado.horas_trabalhadas, HORAS_FRANQUIA_PADRAO),
            servico_config=cls.extract_servico_config(chamado.catalogo_servico, tecnico),
            fornecedor_peca=getattr(chamado, 'fornecedor_peca', None),
            custo_peca=td(chamado.custo_peca),
            _original=chamado
        )
        
        key_atual = cls.get_lote_key(chamado_input_atual)

        # 2. Buscar outros chamados do mesmo tecnico/data (candidatos a lote)
        outros_chamados = ChamadoModel.query.filter(
            ChamadoModel.tecnico_id == chamado.tecnico_id,
            ChamadoModel.data_atendimento == chamado.data_atendimento,
            ChamadoModel.status_chamado == 'Concluído',
            ChamadoModel.status_validacao == 'Aprovado',
            ChamadoModel.id != chamado.id
        ).all()

        # 3. Converter outros chamados para Inputs e filtrar pelo mesmo Lote Key
        inputs_lote = [chamado_input_atual]
        
        for outro in outros_chamados:
            outro_input = ChamadoInput(
                id=outro.id,
                data_atendimento=outro.data_atendimento,
                cidade=outro.cidade or outro.loja or "INDEFINIDO",
                loja=outro.loja,
                horas_trabalhadas=td(outro.horas_trabalhadas, HORAS_FRANQUIA_PADRAO),
                servico_config=cls.extract_servico_config(outro.catalogo_servico, tecnico),
                fornecedor_peca=getattr(outro, 'fornecedor_peca', None),
                custo_peca=td(outro.custo_peca),
                _original=outro
            )
            
            # So adiciona se pertencer ao mesmo grupo (cidade/loja normalizada)
            if cls.get_lote_key(outro_input) == key_atual:
                inputs_lote.append(outro_input)

        # 4. Calcular Custos em Lote (Motor Unificado)
        resultados = cls.calcular_custos_lote(inputs_lote)
        
        # 5. Retornar resultado do chamado atual
        resultado_atual = resultados.get(chamado_input_atual.id)
        
        if not resultado_atual:
            # Fallback de seguranca (nao deveria ocorrer)
            return chamado_input_atual.servico_config.valor_custo_tecnico
            
        return resultado_atual.custo_total

    # --------------------------------------------------------------------------
    # LPU DO CONTRATO (Single Source of Pricing)
    # --------------------------------------------------------------------------

    @staticmethod
    def get_valor_peca(contrato_id: int, item_lpu_id: int) -> Decimal:
        """
        Retorna o valor de venda de uma peca para um contrato especifico.
        Retorna Decimal.
        """
        import logging
        from src.models import ContratoItem, ItemLPU, Cliente
        
        logger = logging.getLogger(__name__)

        # Buscar preco EXCLUSIVAMENTE no contrato
        contrato_item = ContratoItem.query.filter_by(
            cliente_id=contrato_id,
            item_lpu_id=item_lpu_id,
            ativo=True
        ).first()

        if contrato_item:
            # ContratoItem deve ter Numeric, que vem como Decimal or float depending on driver.
            # Safest is to cast.
            return Decimal(str(contrato_item.valor_venda or '0.00'))

        # SEM FALLBACK: Item nao precificado - registrar warning e notificar Admins
        item = ItemLPU.query.get(item_lpu_id)
        cliente = Cliente.query.get(contrato_id)
        
        item_nome = item.nome if item else f"ID-{item_lpu_id}"
        cliente_nome = cliente.nome if cliente else f"ID-{contrato_id}"
        
        msg_alerta = (
            f"[PRICING] Item nao precificado: '{item_nome}' "
            f"para cliente '{cliente_nome}'. Valor R$ 0,00 aplicado."
        )
        
        logger.warning(msg_alerta)
        
        # Criar notificacao para admins e financeiro
        try:
            from src.models import User, Notification, db
            admins = User.query.filter(User.role.in_(['Admin', 'Financeiro'])).all()
            for admin in admins:
                notificacao = Notification(
                    user_id=admin.id,
                    title="Alerta de Precificação (R$ 0,00)",
                    message=msg_alerta,
                    notification_type="warning"
                )
                db.session.add(notificacao)
            # Flush para garantir persistencia no contexto da transacao atual
            db.session.flush()
        except Exception as e:
            logger.error(f"Erro ao criar notificacao de pricing: {e}")
        
        return Decimal('0.00')

    @staticmethod
    def get_valor_peca_contrato(cliente_id: int, item_id: int) -> dict:
        """
        Busca o valor de venda de uma peca para um cliente especifico.
        Retorna Decimal nos campos monetarios.
        """
        from src.models import ContratoItem, ItemLPU
        
        td = PricingService._to_decimal

        # Buscar preco EXCLUSIVAMENTE no contrato
        contrato_item = ContratoItem.query.filter_by(
            cliente_id=cliente_id,
            item_lpu_id=item_id,
            ativo=True
        ).first()

        if contrato_item:
            return {
                'valor_venda': td(contrato_item.valor_venda),
                'valor_repasse': td(contrato_item.valor_repasse),
                'valor_custo': td(contrato_item.item_lpu.valor_custo) if contrato_item.item_lpu else Decimal('0.00'),
                'is_precificado': True,
                'margem': td(contrato_item.margem)
            }

        # SEM FALLBACK: Buscar apenas custo de referencia
        item = ItemLPU.query.get(item_id)
        return {
            'valor_venda': Decimal('0.00'),
            'valor_repasse': None,
            'valor_custo': td(item.valor_custo) if item else Decimal('0.00'),
            'is_precificado': False,
            'margem': Decimal('0.00')
        }

    @staticmethod
    def get_tabela_precos_contrato(cliente_id: int) -> list:
        """
        Retorna a tabela de precos para um cliente.
        """
        from src.models import ContratoItem
        td = PricingService._to_decimal

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
                'valor_venda': td(ci.valor_venda),
                'valor_repasse': td(ci.valor_repasse),
                'valor_custo': td(item.valor_custo),
                'margem': td(ci.margem),
                'margem_percent': round(td(ci.margem_percent), 1)
            })

        return resultado
