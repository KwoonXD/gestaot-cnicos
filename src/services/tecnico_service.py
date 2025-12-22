from ..models import db, Tecnico, Chamado
from datetime import datetime

class TecnicoService:
    @staticmethod
    def get_all(filters=None):
        query = Tecnico.query
        if filters:
            if filters.get('estado'):
                query = query.filter_by(estado=filters['estado'])
            if filters.get('cidade'):
                query = query.filter(Tecnico.cidade.ilike(f"%{filters['cidade']}%"))
            if filters.get('status'):
                query = query.filter_by(status=filters['status'])
            if filters.get('search'):
                query = query.filter(Tecnico.nome.ilike(f"%{filters['search']}%"))
        
        tecnicos = query.order_by(Tecnico.nome).all()
        
        # Post-query filtering for properties not in DB directly can be expensive but needed for 'pagamento pending'
        if filters and filters.get('pagamento'):
            if filters['pagamento'] == 'Pendente':
                tecnicos = [t for t in tecnicos if t.total_a_pagar > 0]
            elif filters['pagamento'] == 'Pago':
                tecnicos = [t for t in tecnicos if t.total_a_pagar == 0]
                
        return tecnicos

    @staticmethod
    def get_by_id(id):
        return Tecnico.query.get_or_404(id)

    @staticmethod
    def create(data):
        tecnico = Tecnico(
            nome=data['nome'],
            contato=data['contato'],
            cidade=data['cidade'],
            estado=data['estado'],
            status=data.get('status', 'Ativo'),
            valor_por_atendimento=float(data.get('valor_por_atendimento', 150.00)),
            forma_pagamento=data.get('forma_pagamento', ''),
            chave_pagamento=data.get('chave_pagamento', ''),
            tecnico_principal_id=data.get('tecnico_principal_id'),
            data_inicio=datetime.strptime(data['data_inicio'], '%Y-%m-%d').date()
        )
        db.session.add(tecnico)
        db.session.commit()
        return tecnico

    @staticmethod
    def update(id, data):
        tecnico = TecnicoService.get_by_id(id)
        tecnico.nome = data['nome']
        tecnico.contato = data['contato']
        tecnico.cidade = data['cidade']
        tecnico.estado = data['estado']
        tecnico.status = data.get('status', 'Ativo')
        tecnico.valor_por_atendimento = float(data.get('valor_por_atendimento', 150.00))
        tecnico.forma_pagamento = data.get('forma_pagamento', '')
        tecnico.chave_pagamento = data.get('chave_pagamento', '')
        tecnico.tecnico_principal_id = data.get('tecnico_principal_id')
        tecnico.data_inicio = datetime.strptime(data['data_inicio'], '%Y-%m-%d').date()
        db.session.commit()
        return tecnico

    @staticmethod
    def get_stats():
        return {
            'ativos': Tecnico.query.filter_by(status='Ativo').count(),
            'total_pendente': sum(t.total_a_pagar for t in Tecnico.query.all())
        }

    @staticmethod
    def get_pendencias(id):
        tecnico = TecnicoService.get_by_id(id)
        # Use simple property or query logic.
        # Assuming Chamado has 'pago' boolean field.
        return Chamado.query.filter_by(tecnico_id=id, pago=False).order_by(Chamado.data_atendimento.desc()).all()
