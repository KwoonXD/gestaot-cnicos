from ..models import db, Tecnico, Chamado, Tag
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case, and_
from marshmallow import Schema, fields, validate, ValidationError

# Validation Schema
class TecnicoSchema(Schema):
    nome = fields.Str(required=True, validate=validate.Length(min=3))
    documento = fields.Str(allow_none=True)
    contato = fields.Str(required=True)
    cidade = fields.Str(required=True)
    estado = fields.Str(required=True, validate=validate.Length(equal=2))
    status = fields.Str(load_default='Ativo')
    valor_por_atendimento = fields.Float(load_default=120.00)
    valor_adicional_loja = fields.Float(load_default=20.00)
    valor_hora_adicional = fields.Float(load_default=30.00)
    forma_pagamento = fields.Str(allow_none=True)
    chave_pagamento = fields.Str(allow_none=True)
    tecnico_principal_id = fields.Int(allow_none=True)
    data_inicio = fields.Date(required=True, format='%Y-%m-%d')

tecnico_schema = TecnicoSchema()

class TecnicoService:
    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        # 1. Subquery for OWN pending totals
        sq_chamados = db.session.query(
            Chamado.tecnico_id,
            func.count(Chamado.id).label('qtd_pendente'),
            func.sum(Chamado.valor).label('valor_pendente')
        ).filter(
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.status_validacao == 'Aprovado',
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ).group_by(Chamado.tecnico_id).subquery()

        # 2. Subquery for AGGREGATED (Sub-technicians) totals
        # We join sq_chamados with Tecnico to sum values of tecnicos that have 'me' as principal
        sq_agregado = db.session.query(
            Tecnico.tecnico_principal_id,
            func.sum(sq_chamados.c.qtd_pendente).label('qtd_sub'),
            func.sum(sq_chamados.c.valor_pendente).label('valor_sub')
        ).join(
            sq_chamados, Tecnico.id == sq_chamados.c.tecnico_id
        ).filter(
            Tecnico.tecnico_principal_id.isnot(None)
        ).group_by(Tecnico.tecnico_principal_id).subquery()

        # 3. Main Query
        query = db.session.query(
            Tecnico,
            func.coalesce(sq_chamados.c.qtd_pendente, 0).label('own_qtd'),
            func.coalesce(sq_chamados.c.valor_pendente, 0.0).label('own_val'),
            func.coalesce(sq_agregado.c.qtd_sub, 0).label('sub_qtd'),
            func.coalesce(sq_agregado.c.valor_sub, 0.0).label('sub_val')
        ).outerjoin(
            sq_chamados, Tecnico.id == sq_chamados.c.tecnico_id
        ).outerjoin(
            sq_agregado, Tecnico.id == sq_agregado.c.tecnico_principal_id
        ).options(joinedload(Tecnico.tags))
        
        # Filters
        if filters:
            if filters.get('estado'):
                query = query.filter(Tecnico.estado == filters['estado'])
            if filters.get('cidade'):
                query = query.filter(Tecnico.cidade.ilike(f"%{filters['cidade']}%"))
            if filters.get('status'):
                query = query.filter(Tecnico.status == filters['status'])
            if filters.get('search'):
                query = query.filter(Tecnico.nome.ilike(f"%{filters['search']}%"))
            if filters.get('tag'):
                query = query.join(Tag).filter(Tag.nome == filters['tag'])
            
        # Filter calculation logic
            total_calc = func.coalesce(sq_chamados.c.valor_pendente, 0) + func.coalesce(sq_agregado.c.valor_sub, 0)

            if filters.get('pagamento') == 'Pendente':
                # Filter tecnicos that have > 0 to collect
                query = query.filter(total_calc > 0)
            
            elif filters.get('pagamento') == 'Pago':
                # Filter tecnicos that have nothing to collect
                query = query.filter(total_calc == 0)

        # Order
        query = query.order_by(Tecnico.nome)

        if page is None:
            # Retorna lista completa (para relatórios e selects)
            items_raw = query.all()
            final_items = []
            for row in items_raw:
                # row é uma tupla (Tecnico, own_qtd, own_val, sub_qtd, sub_val)
                tecnico, o_q, o_v, s_q, s_v = row
                
                if tecnico.tecnico_principal_id:
                    tecnico.total_atendimentos_nao_pagos = 0
                    tecnico.total_a_pagar = 0.0
                    tecnico.total_agregado = 0.0
                else:
                    tecnico.total_atendimentos_nao_pagos = int(o_q + s_q)
                    tecnico.total_a_pagar = float(o_v + s_v)
                    tecnico.total_agregado = float(o_v + s_v)
                
                final_items.append(tecnico)
            return final_items
        else:
            # Retorna Objeto Pagination (para telas de listagem)
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            
            new_items = []
            for row in pagination.items:
                # row is a tuple (Tecnico, own_qtd, own_val, sub_qtd, sub_val)
                tecnico, o_q, o_v, s_q, s_v = row
                
                if tecnico.tecnico_principal_id:
                    tecnico.total_atendimentos_nao_pagos = 0
                    tecnico.total_a_pagar = 0.0
                    tecnico.total_agregado = 0.0
                else:
                    tecnico.total_atendimentos_nao_pagos = int(o_q + s_q)
                    tecnico.total_a_pagar = float(o_v + s_v)
                    tecnico.total_agregado = float(o_v + s_v)
                
                new_items.append(tecnico)
                
            pagination.items = new_items
            return pagination

    @staticmethod
    def get_by_id(id):
        tecnico = Tecnico.query.options(joinedload(Tecnico.tags)).get_or_404(id)
        
        if tecnico.tecnico_principal_id:
            tecnico.total_a_pagar = 0.0
            tecnico.total_atendimentos_nao_pagos = 0
            tecnico.total_agregado = 0.0
        else:
            # Calculate manually using DB optimized queries
            # Own
            own_pending = Chamado.query.with_entities(func.sum(Chamado.valor), func.count(Chamado.id)).filter(
                Chamado.tecnico_id == id,
                Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                Chamado.status_validacao == 'Aprovado',
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).first()
            
            own_val = own_pending[0] or 0.0
            own_cnt = own_pending[1] or 0
            
            # Subs
            sub_val = 0.0
            sub_cnt = 0
            if tecnico.sub_tecnicos:
                for sub in tecnico.sub_tecnicos:
                     sp = Chamado.query.with_entities(func.sum(Chamado.valor), func.count(Chamado.id)).filter(
                        Chamado.tecnico_id == sub.id,
                        Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                        Chamado.status_validacao == 'Aprovado',
                        Chamado.pago == False,
                        Chamado.pagamento_id == None
                     ).first()
                     sub_val += (sp[0] or 0.0)
                     sub_cnt += (sp[1] or 0)
            
            tecnico.total_a_pagar = float(own_val + sub_val)
            tecnico.total_atendimentos_nao_pagos = int(own_cnt + sub_cnt)
            tecnico.total_agregado = tecnico.total_a_pagar
            
        return tecnico

    @staticmethod
    def create(data):
        try:
            val_data = tecnico_schema.load(data)
        except ValidationError as err:
            raise ValueError(f"Erro de validação: {err.messages}")

        tecnico = Tecnico(**val_data)
        db.session.add(tecnico)
        db.session.commit()
        return tecnico

    @staticmethod
    def update(id, data):
        tecnico = TecnicoService.get_by_id(id)
        
        try:
            val_data = tecnico_schema.load(data, partial=True)
        except ValidationError as err:
            raise ValueError(f"Erro de validação: {err.messages}")

        for key, value in val_data.items():
            setattr(tecnico, key, value)
            
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
            'total_pendente': db.session.query(func.sum(Chamado.valor)).filter(
                Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                Chamado.status_validacao == 'Aprovado',
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).scalar() or 0.0
        }

    @staticmethod
    def get_pendencias(id):
        tecnico = TecnicoService.get_by_id(id)
        
        # Get own pending calls
        chamados_proprios = Chamado.query.filter(
            Chamado.tecnico_id == id,
            Chamado.pago == False,
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.status_validacao == 'Aprovado',
            Chamado.pagamento_id == None
        ).order_by(Chamado.data_atendimento.desc()).all()
        
        # Get sub-technicians' pending calls
        chamados_sub = []
        for sub in tecnico.sub_tecnicos:
            chamados_sub.extend(sub.chamados.filter(
                Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                Chamado.status_validacao == 'Aprovado',
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).order_by(Chamado.data_atendimento.desc()).all())
            
        # Combine and sort by date descending
        todos_chamados = chamados_proprios + chamados_sub
        todos_chamados.sort(key=lambda x: x.data_atendimento, reverse=True)
        
        return todos_chamados
