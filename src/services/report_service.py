from ..models import db, Chamado, Tecnico, CatalogoServico, ItemLPU, StockMovement
from sqlalchemy import func, text, case, and_, extract
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal


class ReportService:
    """
    Serviço centralizado para queries pesadas de relatórios e KPIs.
    Otimizado para performance com SQL direto quando necessário.
    """

    # =========================================================================
    # KPIs DE LUCRATIVIDADE (ROI) - FASE 2
    # =========================================================================

    @staticmethod
    def margem_contribuicao_global(inicio: date = None, fim: date = None) -> dict:
        """
        Calcula a Margem de Contribuição Global do período.

        Fórmula: Receita Total - Custos Totais (Técnico + Peças)

        Returns:
            {
                'receita_total': float,
                'custo_tecnico': float,
                'custo_pecas': float,
                'custo_total': float,
                'margem': float,
                'margem_percent': float,
                'volume': int
            }
        """
        if not inicio:
            today = date.today()
            inicio = date(today.year, today.month, 1)
        if not fim:
            fim = date.today()

        # Apenas chamados Concluídos ou SPARE (válidos para financeiro)
        result = db.session.query(
            func.count(Chamado.id).label('volume'),
            func.coalesce(func.sum(Chamado.valor_receita_total), 0).label('receita_total'),
            func.coalesce(func.sum(Chamado.custo_atribuido), 0).label('custo_tecnico'),
            # custo_peca só conta se fornecedor_peca = 'Empresa'
            func.coalesce(func.sum(
                case(
                    (Chamado.fornecedor_peca == 'Empresa', Chamado.custo_peca),
                    else_=0
                )
            ), 0).label('custo_pecas')
        ).filter(
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.data_atendimento >= inicio,
            Chamado.data_atendimento <= fim
        ).first()

        receita = float(result.receita_total or 0)
        custo_tecnico = float(result.custo_tecnico or 0)
        custo_pecas = float(result.custo_pecas or 0)
        custo_total = custo_tecnico + custo_pecas
        margem = receita - custo_total
        margem_pct = (margem / receita * 100) if receita > 0 else 0.0

        return {
            'receita_total': round(receita, 2),
            'custo_tecnico': round(custo_tecnico, 2),
            'custo_pecas': round(custo_pecas, 2),
            'custo_total': round(custo_total, 2),
            'margem': round(margem, 2),
            'margem_percent': round(margem_pct, 1),
            'volume': int(result.volume or 0)
        }

    @staticmethod
    def tecnico_mais_rentavel(inicio: date = None, fim: date = None, limit: int = 5) -> list:
        """
        Identifica os técnicos com maior margem líquida (não apenas faturamento bruto).

        Fórmula por técnico:
        Margem = Receita gerada - Custo pago ao técnico - Custo peças (empresa)

        Returns:
            [
                {
                    'tecnico_id': int,
                    'nome': str,
                    'volume': int,
                    'receita': float,
                    'custo_servico': float,
                    'custo_pecas': float,
                    'margem': float,
                    'margem_percent': float,
                    'ticket_medio': float
                }
            ]
        """
        if not inicio:
            today = date.today()
            inicio = date(today.year, today.month, 1)
        if not fim:
            fim = date.today()

        # Subquery para agregar por técnico
        results = db.session.query(
            Chamado.tecnico_id,
            Tecnico.nome,
            func.count(Chamado.id).label('volume'),
            func.coalesce(func.sum(Chamado.valor_receita_total), 0).label('receita'),
            func.coalesce(func.sum(Chamado.custo_atribuido), 0).label('custo_servico'),
            func.coalesce(func.sum(
                case(
                    (Chamado.fornecedor_peca == 'Empresa', Chamado.custo_peca),
                    else_=0
                )
            ), 0).label('custo_pecas')
        ).join(
            Tecnico, Chamado.tecnico_id == Tecnico.id
        ).filter(
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.data_atendimento >= inicio,
            Chamado.data_atendimento <= fim
        ).group_by(
            Chamado.tecnico_id, Tecnico.nome
        ).having(
            func.count(Chamado.id) > 0  # Evita técnicos sem chamados
        ).all()

        data = []
        for r in results:
            receita = float(r.receita or 0)
            custo_servico = float(r.custo_servico or 0)
            custo_pecas = float(r.custo_pecas or 0)
            custo_total = custo_servico + custo_pecas
            margem = receita - custo_total
            margem_pct = (margem / receita * 100) if receita > 0 else 0.0
            volume = int(r.volume)
            ticket_medio = (receita / volume) if volume > 0 else 0.0

            data.append({
                'tecnico_id': r.tecnico_id,
                'nome': r.nome,
                'volume': volume,
                'receita': round(receita, 2),
                'custo_servico': round(custo_servico, 2),
                'custo_pecas': round(custo_pecas, 2),
                'margem': round(margem, 2),
                'margem_percent': round(margem_pct, 1),
                'ticket_medio': round(ticket_medio, 2)
            })

        # Ordenar por margem (maior para menor)
        data.sort(key=lambda x: x['margem'], reverse=True)
        return data[:limit]

    @staticmethod
    def ofensor_custos(inicio: date = None, fim: date = None, limit: int = 5) -> list:
        """
        Identifica os itens de estoque (peças) que mais consumiram verba no período.

        Considera movimentações de tipo 'USO' vinculadas a chamados,
        multiplicando pela quantidade e custo unitário.

        Returns:
            [
                {
                    'item_id': int,
                    'nome': str,
                    'valor_custo_unitario': float,
                    'quantidade_consumida': int,
                    'custo_total': float,
                    'ocorrencias': int  # Em quantos chamados apareceu
                }
            ]
        """
        if not inicio:
            today = date.today()
            inicio = date(today.year, today.month, 1)
        if not fim:
            fim = date.today()

        # Buscar movimentações de USO no período
        results = db.session.query(
            ItemLPU.id,
            ItemLPU.nome,
            ItemLPU.valor_custo,
            func.sum(StockMovement.quantidade).label('quantidade_consumida'),
            func.count(func.distinct(StockMovement.chamado_id)).label('ocorrencias')
        ).join(
            StockMovement, StockMovement.item_lpu_id == ItemLPU.id
        ).filter(
            StockMovement.tipo_movimento == 'USO',
            StockMovement.data_criacao >= inicio,
            StockMovement.data_criacao <= fim
        ).group_by(
            ItemLPU.id, ItemLPU.nome, ItemLPU.valor_custo
        ).all()

        data = []
        for r in results:
            custo_unit = float(r.valor_custo or 0)
            qtd = int(r.quantidade_consumida or 0)
            custo_total = custo_unit * qtd

            data.append({
                'item_id': r.id,
                'nome': r.nome,
                'valor_custo_unitario': round(custo_unit, 2),
                'quantidade_consumida': qtd,
                'custo_total': round(custo_total, 2),
                'ocorrencias': int(r.ocorrencias or 0)
            })

        # Ordenar por custo total (maior para menor)
        data.sort(key=lambda x: x['custo_total'], reverse=True)
        return data[:limit]

    @staticmethod
    def kpis_dashboard(inicio: date = None, fim: date = None) -> dict:
        """
        Retorna todos os KPIs de ROI consolidados para o dashboard.
        Otimizado para uma única chamada.

        Returns:
            {
                'margem_global': {...},
                'top_tecnicos_rentaveis': [...],
                'top_ofensores_custo': [...]
            }
        """
        margem = ReportService.margem_contribuicao_global(inicio, fim)

        # Adiciona flag de alerta crítico
        margem['alerta_critico'] = margem['margem_percent'] < 15

        return {
            'margem_global': margem,
            'top_tecnicos_rentaveis': ReportService.tecnico_mais_rentavel(inicio, fim, limit=3),
            'top_ofensores_custo': ReportService.ofensor_custos(inicio, fim, limit=5)
        }

    @staticmethod
    def evolucao_margem(meses: int = 6) -> list:
        """
        Retorna evolução mensal da margem de contribuição.

        Args:
            meses: Quantidade de meses para trás (default: 6)

        Returns:
            [
                {
                    'mes': '2024-01',
                    'mes_label': 'Jan/24',
                    'receita': float,
                    'custo_tecnico': float,
                    'custo_pecas': float,
                    'custo_total': float,
                    'margem': float,
                    'margem_percent': float,
                    'volume': int
                }
            ]
        """
        hoje = date.today()
        data = []

        for i in range(meses - 1, -1, -1):
            # Calcular primeiro e último dia do mês
            mes_ref = hoje - relativedelta(months=i)
            inicio_mes = date(mes_ref.year, mes_ref.month, 1)

            # Último dia do mês
            if mes_ref.month == 12:
                fim_mes = date(mes_ref.year + 1, 1, 1) - relativedelta(days=1)
            else:
                fim_mes = date(mes_ref.year, mes_ref.month + 1, 1) - relativedelta(days=1)

            # Query para o mês
            result = db.session.query(
                func.count(Chamado.id).label('volume'),
                func.coalesce(func.sum(Chamado.valor_receita_total), 0).label('receita'),
                func.coalesce(func.sum(Chamado.custo_atribuido), 0).label('custo_tecnico'),
                func.coalesce(func.sum(
                    case(
                        (Chamado.fornecedor_peca == 'Empresa', Chamado.custo_peca),
                        else_=0
                    )
                ), 0).label('custo_pecas')
            ).filter(
                Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                Chamado.data_atendimento >= inicio_mes,
                Chamado.data_atendimento <= fim_mes
            ).first()

            receita = float(result.receita or 0)
            custo_tecnico = float(result.custo_tecnico or 0)
            custo_pecas = float(result.custo_pecas or 0)
            custo_total = custo_tecnico + custo_pecas
            margem = receita - custo_total
            margem_pct = (margem / receita * 100) if receita > 0 else 0.0

            # Labels
            meses_pt = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                       'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            mes_label = f"{meses_pt[mes_ref.month - 1]}/{str(mes_ref.year)[2:]}"

            data.append({
                'mes': inicio_mes.strftime('%Y-%m'),
                'mes_label': mes_label,
                'receita': round(receita, 2),
                'custo_tecnico': round(custo_tecnico, 2),
                'custo_pecas': round(custo_pecas, 2),
                'custo_total': round(custo_total, 2),
                'margem': round(margem, 2),
                'margem_percent': round(margem_pct, 1),
                'volume': int(result.volume or 0)
            })

        return data

    @staticmethod
    def ranking_tecnicos_completo(inicio: date = None, fim: date = None) -> list:
        """
        Retorna ranking completo de técnicos com métricas de rentabilidade.
        Usado para drill-down e análises detalhadas.

        Returns:
            Lista completa de técnicos ordenados por margem (sem limit).
        """
        return ReportService.tecnico_mais_rentavel(inicio, fim, limit=100)

    # =========================================================================
    # RELATÓRIOS GEOGRÁFICOS (EXISTENTE)
    # =========================================================================

    @staticmethod
    def rentabilidade_geografica(inicio, fim, cliente_id=None):
        """
        Calcula rentabilidade por Cidade/Estado.
        Retorna lista de dicts:
        {
            'cidade': 'Guarabira',
            'estado': 'PB',
            'volume': 10,
            'receita': 1200.0,
            'custo': 800.0,
            'margem': 400.0,
            'margem_percent': 33.3,
            'cma': 80.0 (Custo Médio por Atendimento)
        }
        """
        query = db.session.query(
            Chamado.cidade,
            Tecnico.estado,
            func.count(Chamado.id).label('volume'),
            func.sum(Chamado.valor_receita_total).label('receita'),
            func.sum(Chamado.custo_atribuido + func.coalesce(Chamado.custo_peca, 0)).label('custo')
        ).join(Chamado.tecnico)

        if cliente_id:
            query = query.join(Chamado.catalogo_servico).filter(CatalogoServico.cliente_id == cliente_id)

        query = query.filter(
            Chamado.status_chamado == 'Concluído',
            Chamado.data_atendimento >= inicio,
            Chamado.data_atendimento <= fim
        ).group_by(Chamado.cidade, Tecnico.estado)

        results = query.all()

        data = []
        for r in results:
            receita = float(r.receita or 0)
            custo = float(r.custo or 0)
            margem = receita - custo
            margem_pct = (margem / receita * 100) if receita > 0 else 0.0
            volume = int(r.volume)
            cma = (custo / volume) if volume > 0 else 0.0

            data.append({
                'cidade': r.cidade,
                'estado': r.estado,
                'volume': volume,
                'receita': receita,
                'custo': custo,
                'margem': margem,
                'margem_percent': round(margem_pct, 1),
                'cma': round(cma, 2)
            })

        # Ordenar por Receita desc
        data.sort(key=lambda x: x['receita'], reverse=True)
        return data
