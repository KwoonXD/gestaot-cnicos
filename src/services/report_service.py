from ..models import db, Chamado, Tecnico, CatalogoServico
from sqlalchemy import func, text
from datetime import datetime

class ReportService:
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
            Tecnico.estado, # Usa estado do técnico como proxy para o chamado? Ou tem estado no chamado?
            # Chamado não tem estado explicito. Tecnico tem.
            # Mas o tecnico pode viajar. Ideal seria Chamado.estado ou inferir.
            # Vamos usar Tecnico.estado por enquanto.
            func.count(Chamado.id).label('volume'),
            func.sum(Chamado.valor_receita_total).label('receita'),
            func.sum(Chamado.custo_atribuido + Chamado.custo_peca).label('custo')
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
            
        # Ordenar por margem percentual (menor para maior? user wants red <10%)
        # Geralmente queremos ver os ruins primeiro? Ou apenas list.
        # Ordenar por Receita desc
        data.sort(key=lambda x: x['receita'], reverse=True)
        return data
