from ..models import db, Tecnico, Chamado, Tag
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
            
            if filters.get('tag'):
                # Filtro por Tag (nome exato)
                query = query.join(Tag).filter(Tag.nome == filters['tag'])
            
            # Filtro Avançado: Pagamento (Recuperado via SQL)
            if filters.get('pagamento') == 'Pendente':
                # Filtra técnicos que possuem pelo menos um chamado Concluído e Não Pago
                query = query.join(Chamado).filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.pago == False,
                    Chamado.pagamento_id == None,
                    Tecnico.tecnico_principal_id == None
                ).group_by(Tecnico.id)
            
            elif filters.get('pagamento') == 'Pago':
                # Filtra técnicos que NÃO estão no grupo de pendentes (usando NOT IN ou LEFT JOIN null)
                # Para performance simples neste estágio, vamos usar except_
                pendentes_subquery = db.session.query(Tecnico.id).join(Chamado).filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.pago == False,
                    Chamado.pagamento_id == None,
                    Tecnico.tecnico_principal_id == None
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
    def delete(id, user_id):
        tecnico = TecnicoService.get_by_id(id)
        
        # Security Check: Dependencies
        if tecnico.pagamentos.count() > 0:
            raise ValueError("Este técnico possui histórico de pagamentos. Use a opção 'Inativar' em vez de excluir.")
            
        if tecnico.chamados.count() > 0:
             raise ValueError("Este técnico possui chamados vinculados. Reatribua os chamados ou use 'Inativar'.")

        # Audit
        from .audit_service import AuditService
        AuditService.log_change(
            model_name='Tecnico',
            object_id=tecnico.id,
            action='DELETE',
            changes=f"Deleted Tecnico {tecnico.nome} (ID: {tecnico.id_tecnico})"
        )
        
        db.session.delete(tecnico)
        db.session.commit()

    @staticmethod
    def get_stats():
        return {
            'ativos': Tecnico.query.filter_by(status='Ativo').count(),
            'total_pendente': sum(t.total_a_pagar for t in Tecnico.query.all())
        }

    @staticmethod
    def get_pendencias(id):
        tecnico = TecnicoService.get_by_id(id)
        
        # Get own pending calls
        chamados_proprios = Chamado.query.filter(
            Chamado.tecnico_id == id,
            Chamado.pago == False,
            Chamado.status_chamado == 'Concluído',
            Chamado.pagamento_id == None
        ).order_by(Chamado.data_atendimento.desc()).all()
        
        # Get sub-technicians' pending calls
        chamados_sub = []
        for sub in tecnico.sub_tecnicos:
            chamados_sub.extend(sub.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).order_by(Chamado.data_atendimento.desc()).all())
            
        # Combine and sort by date descending
        todos_chamados = chamados_proprios + chamados_sub
        todos_chamados.sort(key=lambda x: x.data_atendimento, reverse=True)
        
        return todos_chamados
