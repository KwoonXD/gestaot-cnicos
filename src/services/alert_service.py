from datetime import datetime, timedelta
from src.models import db, Chamado, Tecnico

class AlertService:
    @staticmethod
    def get_alerts():
        alerts = []
        hoje = datetime.now().date()
        date_30_days_ago = hoje - timedelta(days=30)
        
        # Alert 1: Chamados pendentes de pagamento há > 30 dias
        chamados_atrasados = Chamado.query.filter_by(status_chamado='Concluído', pago=False)\
            .filter(Chamado.data_atendimento < date_30_days_ago)\
            .all()
            
        count_atrasados = len(chamados_atrasados)
        if count_atrasados > 0:
            alerts.append({
                'tipo': 'danger',
                'msg': f'Existem {count_atrasados} chamados concluídos há mais de 30 dias não pagos.',
                'link': '/operacional/chamados?status=Concluído&pago=False' # Assuming link structure
            })
            
        # Alert 2: Técnicos com acumulado > 2000
        # This is expensive if we iterate all technicians. Better to do aggregation query if possible.
        # But efficiently, we can check technicians with unpaid chamados.
        # Since 'total_a_pagar' computes on the fly, let's just iterate active technicians or do a group by query.
        
        # Efficient Group By Query
        # Select tecnico_id, sum(valor) from Chamado where status='Concluído' and pago=False group by tecnico_id having sum(valor) > 2000
        from sqlalchemy import func
        
        high_value_tecnicos = db.session.query(
            Chamado.tecnico_id, func.sum(Chamado.valor).label('total')
        ).filter(
            Chamado.status_chamado == 'Concluído',
            Chamado.pago == False
        ).group_by(Chamado.tecnico_id).having(func.sum(Chamado.valor) > 2000).all()
        
        for tec_id, total in high_value_tecnicos:
            # Get Tecnico name
            tecnico = Tecnico.query.get(tec_id)
            if tecnico:
                 alerts.append({
                    'tipo': 'warning',
                    'msg': f'Técnico {tecnico.nome} tem R$ {float(total):.2f} acumulados a receber.',
                    'link': f'/operacional/tecnicos/{tecnico.id}'
                })
        
        return alerts
