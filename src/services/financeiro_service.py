from ..models import db, Pagamento, Chamado, Tecnico, Lancamento
from datetime import datetime, date

class FinanceiroService:
    @staticmethod
    def criar_lancamento(data):
        lancamento = Lancamento(
            tecnico_id=int(data['tecnico_id']),
            tipo=data['tipo'],
            valor=float(data['valor']),
            descricao=data['descricao'],
            data=datetime.strptime(data['data'], '%Y-%m-%d').date() if data.get('data') else date.today()
        )
        db.session.add(lancamento)
        db.session.commit()
        return lancamento

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
        
        # 1. Get closed tickets
        chamados_para_pagar = Chamado.query.filter(
            Chamado.tecnico_id == tecnico_id,
            Chamado.status_chamado == 'Concluído',
            Chamado.pago == False,
            Chamado.data_atendimento >= periodo_inicio,
            Chamado.data_atendimento <= periodo_fim
        ).all()
        
        # 2. Get pending adjustments (Lancamentos)
        # We include lancamentos that are NOT linked to a payment yet
        # OR we could limit by date. Usually adjustments are "pending" until paid.
        # Let's assume we pick up all pending lancamentos for this technician up to the end date
        lancamentos_pendentes = Lancamento.query.filter(
            Lancamento.tecnico_id == tecnico_id,
            Lancamento.pagamento_id == None,
            Lancamento.data <= periodo_fim
        ).all()
        
        if not chamados_para_pagar and not lancamentos_pendentes:
            return None, "Nenhum chamado ou lançamento pendente encontrado para este técnico no período."
            
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
            
        for lancamento in lancamentos_pendentes:
            lancamento.pagamento_id = pagamento.id
            
        db.session.commit()
        return pagamento, None

    @staticmethod
    def gerar_pagamento_lote(dados_lote):
        """
        Gera pagamentos para uma lista de técnicos.
        dados_lote: {
            'periodo_inicio': 'YYYY-MM-DD',
            'periodo_fim': 'YYYY-MM-DD',
            'tecnicos_ids': [1, 2, 3]
        }
        """
        generated_count = 0
        errors = []
        
        periodo_inicio = dados_lote['periodo_inicio']
        periodo_fim = dados_lote['periodo_fim']
        
        for tecnico_id in dados_lote['tecnicos_ids']:
            data_individual = {
                'tecnico_id': tecnico_id,
                'periodo_inicio': periodo_inicio,
                'periodo_fim': periodo_fim
            }
            # We reuse the logic, but catch errors to not stop the batch
            try:
                pagamento, error = FinanceiroService.gerar_pagamento(data_individual)
                if pagamento:
                    generated_count += 1
                elif error:
                    # Optional: Log which technicians had no data
                     pass
            except Exception as e:
                errors.append(f"Erro ao gerar para técnico {tecnico_id}: {str(e)}")
                
        return generated_count, errors

    @staticmethod
    def marcar_como_pago(id, observacoes=''):
        pagamento = FinanceiroService.get_by_id(id)
        pagamento.status_pagamento = 'Pago'
        pagamento.data_pagamento = date.today()
        pagamento.observacoes = observacoes
        db.session.commit()
        return pagamento
