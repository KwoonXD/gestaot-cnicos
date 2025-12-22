from ..models import db, Chamado, Tecnico
from datetime import datetime

class ChamadoService:
    @staticmethod
    def get_all(filters=None):
        query = Chamado.query.join(Tecnico)
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter(Chamado.tecnico_id == int(filters['tecnico_id']))
            if filters.get('status'):
                query = query.filter(Chamado.status_chamado == filters['status'])
            if filters.get('tipo'):
                query = query.filter(Chamado.tipo_servico == filters['tipo'])
            if filters.get('pago'):
                if filters['pago'] == 'sim':
                    query = query.filter(Chamado.pago == True)
                elif filters['pago'] == 'nao':
                    query = query.filter(Chamado.pago == False)
                    
        return query.order_by(Chamado.data_atendimento.desc()).all()

    @staticmethod
    def get_by_id(id):
        return Chamado.query.get_or_404(id)

    @staticmethod
    def create(data):
        horario_inicio = data.get('horario_inicio')
        horario_saida = data.get('horario_saida')
        
        chamado = Chamado(
            tecnico_id=int(data['tecnico_id']),
            codigo_chamado=data.get('codigo_chamado', ''),
            data_atendimento=datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date(),
            horario_inicio=datetime.strptime(horario_inicio, '%H:%M').time() if horario_inicio else None,
            horario_saida=datetime.strptime(horario_saida, '%H:%M').time() if horario_saida else None,
            fsa_codes=data.get('fsa_codes', ''),
            tipo_servico=data['tipo_servico'],
            status_chamado=data.get('status_chamado', 'Pendente'),
            valor=float(data.get('valor', 0.0)),
            endereco=data.get('endereco', ''),
            observacoes=data.get('observacoes', '')
        )
        db.session.add(chamado)
        db.session.commit()
        return chamado

    @staticmethod
    def update(id, data):
        chamado = ChamadoService.get_by_id(id)
        horario_inicio = data.get('horario_inicio')
        horario_saida = data.get('horario_saida')
        
        chamado.tecnico_id = int(data['tecnico_id'])
        chamado.codigo_chamado = data.get('codigo_chamado', '')
        chamado.data_atendimento = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
        chamado.horario_inicio = datetime.strptime(horario_inicio, '%H:%M').time() if horario_inicio else None
        chamado.horario_saida = datetime.strptime(horario_saida, '%H:%M').time() if horario_saida else None
        chamado.fsa_codes = data.get('fsa_codes', '')
        chamado.tipo_servico = data['tipo_servico']
        chamado.status_chamado = data.get('status_chamado', 'Pendente')
        chamado.valor = float(data.get('valor', 0.0))
        chamado.endereco = data.get('endereco', '')
        chamado.observacoes = data.get('observacoes', '')
        
        db.session.commit()
        return chamado

    @staticmethod
    def update_status(id, status):
        chamado = ChamadoService.get_by_id(id)
        chamado.status_chamado = status
        db.session.commit()
        return chamado

    @staticmethod
    def get_dashboard_stats():
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        chamados_mes = Chamado.query.filter(
            db.extract('month', Chamado.data_atendimento) == current_month,
            db.extract('year', Chamado.data_atendimento) == current_year
        ).count()
        
        chamados_por_status = {}
        # Avoid direct import of constant to prevent circular dep, or pass it in. 
        # Assuming we can just query distinct or use list.
        # We'll use the query grouping for efficiency in real app, but for now simple:
        for status in ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']:
             chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
             
        return {
            'chamados_mes': chamados_mes,
            'chamados_por_status': chamados_por_status,
            'ultimos': Chamado.query.order_by(Chamado.data_criacao.desc()).limit(5).all()
        }
