"""
StockReportService - Encapsula queries pesadas de relatórios de estoque.

REFATORADO (2026-01): Extraído de stock_routes.py para eliminar Fat Controllers.
Todas as queries de agregação de estoque agora passam por este serviço.
"""
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Any, Optional, NamedTuple
from sqlalchemy import func

from ..models import (
    db, ItemLPU, TecnicoStock, StockMovement, 
    Chamado, Tecnico, SolicitacaoReposicao, ItemLPUPrecoHistorico
)


class UsoPeriodo(NamedTuple):
    """Métricas de uso de peças em um período."""
    total_movs: int
    total_pecas: int


class EstoqueStats(NamedTuple):
    """Estatísticas de estoque em campo."""
    registros: int
    total_pecas: int
    valor_total: Decimal


class StockReportService:
    """
    Serviço para consultas e relatórios de estoque.
    
    Centraliza queries SQL pesadas que antes estavam nas rotas,
    garantindo separação de responsabilidades e melhor testabilidade.
    """

    @staticmethod
    def get_uso_periodo(data_inicio: date, data_fim: date) -> UsoPeriodo:
        """
        Retorna total de peças usadas em um período.
        
        Args:
            data_inicio: Data inicial do período
            data_fim: Data final do período
            
        Returns:
            UsoPeriodo com contagem de movimentações e peças
        """
        result = db.session.query(
            func.count(StockMovement.id).label('total_movs'),
            func.sum(StockMovement.quantidade).label('total_pecas')
        ).filter(
            StockMovement.tipo_movimento == 'USO',
            func.date(StockMovement.data_criacao) >= data_inicio,
            func.date(StockMovement.data_criacao) <= data_fim
        ).first()
        
        return UsoPeriodo(
            total_movs=result.total_movs or 0,
            total_pecas=result.total_pecas or 0
        )

    @staticmethod
    def get_custo_pecas_periodo(data_inicio: date, data_fim: date) -> Decimal:
        """Retorna custo total de peças em chamados no período."""
        result = db.session.query(
            func.sum(Chamado.custo_peca).label('custo_total')
        ).filter(
            Chamado.data_atendimento >= data_inicio,
            Chamado.data_atendimento <= data_fim,
            Chamado.custo_peca > 0
        ).scalar()
        
        return Decimal(str(result)) if result else Decimal('0.00')

    @staticmethod
    def get_top_pecas_usadas(data_inicio: date, data_fim: date, limit: int = 5) -> List[Dict]:
        """Retorna as peças mais usadas no período."""
        results = db.session.query(
            ItemLPU.nome,
            ItemLPU.valor_custo,
            func.sum(StockMovement.quantidade).label('qtd_usada')
        ).join(
            StockMovement, StockMovement.item_lpu_id == ItemLPU.id
        ).filter(
            StockMovement.tipo_movimento == 'USO',
            func.date(StockMovement.data_criacao) >= data_inicio,
            func.date(StockMovement.data_criacao) <= data_fim
        ).group_by(ItemLPU.id).order_by(
            func.sum(StockMovement.quantidade).desc()
        ).limit(limit).all()
        
        return [
            {
                'nome': r.nome,
                'valor_custo': float(r.valor_custo or 0),
                'qtd_usada': r.qtd_usada
            }
            for r in results
        ]

    @staticmethod
    def get_estoque_em_campo() -> EstoqueStats:
        """Retorna estatísticas do estoque atualmente em campo (com técnicos)."""
        result = db.session.query(
            func.count(TecnicoStock.id).label('registros'),
            func.sum(TecnicoStock.quantidade).label('total_pecas'),
            func.sum(TecnicoStock.quantidade * ItemLPU.valor_custo).label('valor_total')
        ).join(
            ItemLPU, TecnicoStock.item_lpu_id == ItemLPU.id
        ).filter(
            TecnicoStock.quantidade > 0
        ).first()
        
        return EstoqueStats(
            registros=result.registros or 0,
            total_pecas=result.total_pecas or 0,
            valor_total=Decimal(str(result.valor_total)) if result.valor_total else Decimal('0.00')
        )

    @staticmethod
    def get_alertas_estoque_baixo(limite: int = 1) -> List[Any]:
        """Retorna registros de técnicos com estoque baixo."""
        return TecnicoStock.query.filter(
            TecnicoStock.quantidade <= limite,
            TecnicoStock.quantidade > 0
        ).all()

    @staticmethod
    def get_movimentacoes_recentes(data_inicio: date, limit: int = 20) -> List[Any]:
        """Retorna movimentações recentes a partir de uma data."""
        return StockMovement.query.filter(
            func.date(StockMovement.data_criacao) >= data_inicio
        ).order_by(StockMovement.data_criacao.desc()).limit(limit).all()

    @staticmethod
    def get_dashboard_resumo() -> Dict[str, Any]:
        """
        Retorna resumo consolidado para o dashboard principal.
        
        Esta é a query unificada que alimenta `/api/dashboard/resumo`.
        """
        hoje = datetime.now().date()
        inicio_mes = hoje.replace(day=1)
        data_30d = hoje - timedelta(days=30)

        # 1. Estoque em campo
        estoque = StockReportService.get_estoque_em_campo()

        # 2. Uso no mês
        uso = StockReportService.get_uso_periodo(inicio_mes, hoje)

        # 3. Custo de materiais no mês
        custo_mes = StockReportService.get_custo_pecas_periodo(inicio_mes, hoje)

        # 4. Alertas
        alertas_baixo = TecnicoStock.query.filter(
            TecnicoStock.quantidade <= 1,
            TecnicoStock.quantidade > 0
        ).count()
        
        solicitacoes_pendentes = SolicitacaoReposicao.query.filter_by(status='Pendente').count()
        
        alteracoes_preco = ItemLPUPrecoHistorico.query.filter(
            func.date(ItemLPUPrecoHistorico.data_alteracao) >= data_30d
        ).count()

        # 5. Top peças do mês
        top_pecas = StockReportService.get_top_pecas_usadas(inicio_mes, hoje, limit=3)

        # 6. Técnicos com mais estoque
        tecnicos_estoque = db.session.query(
            Tecnico.nome,
            func.sum(TecnicoStock.quantidade).label('total')
        ).join(
            TecnicoStock, TecnicoStock.tecnico_id == Tecnico.id
        ).filter(
            TecnicoStock.quantidade > 0
        ).group_by(Tecnico.id).order_by(
            func.sum(TecnicoStock.quantidade).desc()
        ).limit(3).all()

        return {
            'estoque': {
                'total_pecas': estoque.total_pecas,
                'valor_total': float(estoque.valor_total),
                'tecnicos_com_estoque': estoque.registros
            },
            'uso_mes': {
                'movimentacoes': uso.total_movs,
                'pecas_usadas': uso.total_pecas,
                'custo_materiais': float(custo_mes)
            },
            'alertas': {
                'estoque_baixo': alertas_baixo,
                'solicitacoes_pendentes': solicitacoes_pendentes,
                'alteracoes_preco_30d': alteracoes_preco
            },
            'top_pecas_mes': [
                {'nome': p['nome'], 'quantidade': p['qtd_usada']} for p in top_pecas
            ],
            'tecnicos_mais_estoque': [
                {'nome': t.nome, 'quantidade': t.total} for t in tecnicos_estoque
            ],
            'periodo': {
                'inicio_mes': inicio_mes.isoformat(),
                'hoje': hoje.isoformat()
            }
        }

    @staticmethod
    def get_relatorio_periodo(data_inicio: date, data_fim: date) -> Dict[str, Any]:
        """
        Retorna dados para a página de relatório de materiais.
        
        Esta é a query unificada que alimenta `/relatorio`.
        """
        uso = StockReportService.get_uso_periodo(data_inicio, data_fim)
        custo = StockReportService.get_custo_pecas_periodo(data_inicio, data_fim)
        top_pecas = StockReportService.get_top_pecas_usadas(data_inicio, data_fim, limit=5)
        estoque = StockReportService.get_estoque_em_campo()
        movimentacoes = StockReportService.get_movimentacoes_recentes(data_inicio, limit=20)
        alertas = StockReportService.get_alertas_estoque_baixo(limite=1)

        return {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'total_movs': uso.total_movs,
            'total_pecas': uso.total_pecas,
            'custo_periodo': float(custo),
            'top_pecas': top_pecas,
            'estoque_rua': estoque.total_pecas,
            'valor_estoque_rua': float(estoque.valor_total),
            'movimentacoes_recentes': movimentacoes,
            'alertas_estoque': alertas
        }
