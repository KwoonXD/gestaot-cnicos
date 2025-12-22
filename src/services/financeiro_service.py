from datetime import datetime, timedelta
import calendar
from sqlalchemy import func

from src.models import db, Chamado, Pagamento, Tecnico, Lancamento

class FinanceiroService:
    @staticmethod
    def calcular_projecao_mensal():
        hoje = datetime.now()
        ano = hoje.year
        mes = hoje.month
        
        # Último dia do mês
        _, ult_dia = calendar.monthrange(ano, mes)
        
        # Média diária (evitar divisão por zero se for dia 1)
        dia_hoje = hoje.day
        if dia_hoje == 1:
            dia_divisor = 1
        else:
            dia_divisor = dia_hoje
            
        # Total gasto neste mês até agora
        inicio_mes = datetime(ano, mes, 1)
        
        # Query total value of Chamados in current month
        # Assuming we count based on 'data_atendimento' or 'data_criacao'. 
        # User said "total_gasto", usually related to completed services.
        total_atual = db.session.query(func.sum(Chamado.valor))\
            .filter(Chamado.data_atendimento >= inicio_mes)\
            .filter(Chamado.data_atendimento <= hoje)\
            .scalar() or 0.0
            
        total_atual = float(total_atual)
        
        media_diaria = total_atual / dia_divisor
        projecao = media_diaria * ult_dia
        
        return {
            'atual': total_atual,
            'projecao': projecao,
            'media_diaria': media_diaria

        }

    @staticmethod
    def get_pendentes_stats():
        """
        Retorna a quantidade de pagamentos pendentes
        """
        return Pagamento.query.filter_by(status_pagamento='Pendente').count()

    @staticmethod
    def get_all(filters=None):
        query = Pagamento.query
        
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter_by(tecnico_id=filters['tecnico_id'])
            if filters.get('status'):
                query = query.filter_by(status_pagamento=filters['status'])
                
        return query.order_by(Pagamento.data_criacao.desc()).all()

    @staticmethod
    def get_by_id(id):
        return Pagamento.query.get_or_404(id)

    @staticmethod
    def gerar_pagamento(data):
        tecnico_id = data.get('tecnico_id')
        tecnico = Tecnico.query.get(tecnico_id)
        
        if not tecnico:
            return None, "Técnico não encontrado."
            
        # Get unpaid completed chamados
        chamados = tecnico.chamados.filter_by(status_chamado='Concluído', pago=False).all()
        
        if not chamados:
            return None, "Não há chamados pendentes para este técnico."
            
        valor_total = sum(c.valor for c in chamados)
        
        # Determine dates
        if chamados:
            dates = [c.data_atendimento for c in chamados]
            periodo_inicio = min(dates)
            periodo_fim = max(dates)
        else:
            periodo_inicio = datetime.now()
            periodo_fim = datetime.now()
            
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pendente'
        )
        
        db.session.add(pagamento)
        db.session.flush() # get ID
        
        # Link chamados to pagamento
        for c in chamados:
            c.pago = False # Will be true when payment is paid? Or immediately? 
            # Re-reading logic: 'pago' in Chamado usually means "Included in a Payment record that is Paid" OR just "Included in Payment"?
            # Let's assume "Included in Payment" marks it as processed, but 'pago' boolean might be redundant if we check pagamento status.
            # However, typically validation queries check 'pago=False'.
            # If we link to a Pending Payment, is the Chamado 'pago'? Probably not yet.
            c.pagamento_id = pagamento.id
            
        db.session.commit()
        return pagamento, None

    @staticmethod
    def marcar_como_pago(id, observacoes=None):
        pagamento = Pagamento.query.get_or_404(id)
        pagamento.status_pagamento = 'Pago'
        pagamento.data_pagamento = datetime.now()
        if observacoes:
            pagamento.observacoes = observacoes
            
        # Mark all chamados as paid
        for chamado in pagamento.chamados_incluidos:
            chamado.pago = True
            
        db.session.commit()
        return pagamento

    @staticmethod
    def criar_lancamento(data):
        lancamento = Lancamento(
            tecnico_id=data.get('tecnico_id'),
            tipo=data.get('tipo'),
            valor=float(data.get('valor')),
            data=datetime.strptime(data.get('data'), '%Y-%m-%d').date() if data.get('data') else datetime.now().date(),
            descricao=data.get('descricao')
        )
        db.session.add(lancamento)
        db.session.commit()
        return lancamento

    @staticmethod
    def gerar_pagamento_lote(data):
        tecnicos_ids = data.get('tecnicos_ids', [])
        inicio = datetime.strptime(data.get('periodo_inicio'), '%Y-%m-%d').date()
        fim = datetime.strptime(data.get('periodo_fim'), '%Y-%m-%d').date()
        
        count = 0
        errors = []
        
        for t_id in tecnicos_ids:
            tecnico = Tecnico.query.get(t_id)
            if not tecnico: 
                continue
                
            chamados_periodo = tecnico.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.pago == False,
                Chamado.data_atendimento >= inicio,
                Chamado.data_atendimento <= fim
            ).all()
            
            if not chamados_periodo:
                errors.append(f"Técnico {tecnico.nome}: Sem chamados no período.")
                continue
                
            pagamento = Pagamento(
                tecnico_id=tecnico.id,
                periodo_inicio=inicio,
                periodo_fim=fim,
                valor_por_atendimento=tecnico.valor_por_atendimento,
                status_pagamento='Pendente'
            )
            db.session.add(pagamento)
            db.session.flush()
            
            for c in chamados_periodo:
                c.pagamento_id = pagamento.id
                
            count += 1
            
        db.session.commit()
        return count, errors
