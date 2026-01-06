from ..models import db, Tecnico, Chamado, Tag
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case, and_
from marshmallow import Schema, fields, validate, ValidationError, pre_load, EXCLUDE

# Validation Schema
class TecnicoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

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

    @pre_load
    def process_input(self, data, **kwargs):
        # Clean empty strings for Integer/Nullable fields
        if 'tecnico_principal_id' in data and data['tecnico_principal_id'] == '':
            data['tecnico_principal_id'] = None
        return data

tecnico_schema = TecnicoSchema()

class TecnicoService:
    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        # Query Base: Técnicos + Soma de Chamados Pendentes
        # Isso substitui o Ledger com performance igual ou superior.
        
        # 1. Soma condicional (apenas chamados aprovados e não pagos)
        # Use custo_atribuido if available (new logic), else valor (legacy)
        val_term = func.coalesce(Chamado.custo_atribuido, Chamado.valor, 0)
        
        valor_pendente = func.sum(
            case(
                (
                    (Chamado.status_chamado.in_(['Concluído', 'SPARE'])) &
                    (Chamado.status_validacao == 'Aprovado') &
                    (Chamado.pago == False) &
                    (Chamado.pagamento_id == None),
                    val_term
                ),
                else_=0
            )
        ).label('total_pendente')

        # 2. Query Principal com Join
        query = db.session.query(Tecnico, valor_pendente)\
            .outerjoin(Chamado, Tecnico.id == Chamado.tecnico_id)\
            .group_by(Tecnico.id)

        # 3. Filtros
        if filters:
            if filters.get('search'):
                term = f"%{filters['search']}%"
                query = query.filter(
                    (Tecnico.nome.ilike(term)) | 
                    (Tecnico.cidade.ilike(term))
                )
            
            if filters.get('estado'):
                query = query.filter(Tecnico.estado == filters['estado'])

            # Filtro de "Tem algo a receber?" agora é feito no HAVING (pós-soma)
            if filters.get('pagamento') == 'Pendente':
                query = query.having(valor_pendente > 0)
            elif filters.get('pagamento') == 'Pago':
                query = query.having(func.coalesce(valor_pendente, 0) == 0)

        # 4. Paginação
        pagination = query.order_by(Tecnico.nome).paginate(page=page, per_page=per_page)
        
        # 5. Normalização para o Template
        # O SQLAlchemy retorna tuplas (Tecnico, total_pendente). 
        # Vamos injetar o total no objeto para o template não quebrar.
        for tecnico, total in pagination.items:
            tecnico.total_a_pagar_cache = float(total or 0.0)
    
        # Hack para retornar apenas objetos Tecnico na lista, mantendo a paginação
        pagination.items = [t[0] for t in pagination.items]
        
        return pagination

    @staticmethod
    def get_by_id(id):
        tecnico = Tecnico.query.options(joinedload(Tecnico.tags)).get_or_404(id)
        
        if tecnico.tecnico_principal_id:
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
            
            tecnico.total_agregado = float(own_val + sub_val)
            
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
