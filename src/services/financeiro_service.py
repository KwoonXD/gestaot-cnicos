from ..models import db, Pagamento, Chamado, Tecnico
from datetime import datetime, date

class FinanceiroService:
    @staticmethod
    def get_all(filters=None):
        query = Pagamento.query
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter(Pagamento.tecnico_id == int(filters['tecnico_id']))
            if filters.get('status'):
                query = query.filter(Pagamento.status_pagamento == filters['status'])
        
        return query.order_by(Pagamento.data_criacao.desc()).all()

    @staticmethod
    def get_by_id(id):
        return Pagamento.query.get_or_404(id)

    @staticmethod
    def get_pendentes_stats():
        return Pagamento.query.filter_by(status_pagamento='Pendente').count()

    @staticmethod
    def gerar_pagamento(data):
        tecnico_id = int(data['tecnico_id'])
        periodo_inicio = datetime.strptime(data['periodo_inicio'], '%Y-%m-%d').date()
        periodo_fim = datetime.strptime(data['periodo_fim'], '%Y-%m-%d').date()
        
        tecnico = Tecnico.query.get_or_404(tecnico_id)
        
        chamados_para_pagar = Chamado.query.filter(
            Chamado.tecnico_id == tecnico_id,
            Chamado.status_chamado == 'Concluído',
            Chamado.pago == False,
            Chamado.data_atendimento >= periodo_inicio,
            Chamado.data_atendimento <= periodo_fim
        ).all()
        
        if not chamados_para_pagar:
            return None, "Nenhum chamado encontrado para pagamento no período selecionado."
            
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pago',
            data_pagamento=date.today()
        )
        db.session.add(pagamento)
        db.session.flush()
        
        for chamado in chamados_para_pagar:
            chamado.pago = True
            chamado.pagamento_id = pagamento.id
            
        db.session.commit()
        return pagamento, None

    @staticmethod
    def marcar_como_pago(id, observacoes=''):
        pagamento = FinanceiroService.get_by_id(id)
        pagamento.status_pagamento = 'Pago'
        pagamento.data_pagamento = date.today()
        pagamento.observacoes = observacoes
        db.session.commit()
        return pagamento
