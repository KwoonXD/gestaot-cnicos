from ..models import db, Tecnico, Chamado
from datetime import datetime

class TecnicoService:
    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        query = Tecnico.query
        
        if filters:
            # Filtros Simples
            if filters.get('estado'):
                query = query.filter_by(estado=filters['estado'])
            if filters.get('cidade'):
                query = query.filter(Tecnico.cidade.ilike(f"%{filters['cidade']}%"))
            if filters.get('status'):
                query = query.filter_by(status=filters['status'])
            if filters.get('search'):
                query = query.filter(Tecnico.nome.ilike(f"%{filters['search']}%"))
            
            # Filtro Avançado: Pagamento (Recuperado via SQL)
            if filters.get('pagamento') == 'Pendente':
                # Filtra técnicos que possuem pelo menos um chamado Concluído e Não Pago
                query = query.join(Chamado).filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.pago == False
                ).group_by(Tecnico.id)
            
            elif filters.get('pagamento') == 'Pago':
                # Filtra técnicos que NÃO estão no grupo de pendentes (usando NOT IN ou LEFT JOIN null)
                # Para performance simples neste estágio, vamos usar except_
                pendentes_subquery = db.session.query(Tecnico.id).join(Chamado).filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.pago == False
                ).subquery()
                query = query.filter(Tecnico.id.notin_(pendentes_subquery))

        # Ordenação e Paginação
        return query.order_by(Tecnico.nome).paginate(page=page, per_page=per_page, error_out=False)

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
