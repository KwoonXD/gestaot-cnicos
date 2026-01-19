from ..models import db, Tecnico, Chamado, Tag
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case, and_, or_
from marshmallow import Schema, fields, validate, ValidationError, pre_load, EXCLUDE


# ==============================================================================
# DATA CLASS PARA METRICAS AGREGADAS
# ==============================================================================

@dataclass
class TecnicoMetricas:
    """
    Metricas agregadas de um tecnico, calculadas via SQL em batch.
    Substitui as @property que causavam N+1 queries.
    """
    tecnico: Any  # Objeto Tecnico ORM

    # Contadores
    total_atendimentos: int = 0
    total_atendimentos_concluidos: int = 0
    total_atendimentos_nao_pagos: int = 0

    # Valores financeiros
    total_a_pagar: float = 0.0
    total_a_pagar_subs: float = 0.0  # Valor dos sub-tecnicos

    # Datas de pendencias
    oldest_pending_date: Optional[datetime] = None
    newest_pending_date: Optional[datetime] = None

    # Codigos FSA pendentes (lazy loaded se necessario)
    _pending_fsas: Optional[List[str]] = None

    @property
    def total_a_pagar_agregado(self) -> float:
        """Total incluindo sub-tecnicos."""
        return self.total_a_pagar + self.total_a_pagar_subs

    @property
    def total_agregado(self) -> float:
        """Alias para compatibilidade com templates existentes."""
        return self.total_a_pagar_agregado

    @property
    def status_pagamento(self) -> str:
        return "Pendente" if self.total_a_pagar_agregado > 0 else "Pago"

    @property
    def id_tecnico(self) -> str:
        return self.tecnico.id_tecnico

    @property
    def id(self) -> int:
        return self.tecnico.id

    @property
    def nome(self) -> str:
        return self.tecnico.nome

    @property
    def localizacao(self) -> str:
        return self.tecnico.localizacao

    @property
    def pending_fsas(self) -> List[str]:
        """
        Codigos FSA pendentes (lazy loaded).
        Usa TecnicoService para evitar N+1 quando acessado.
        """
        if self._pending_fsas is None:
            # Lazy load usando o Service
            self._pending_fsas = TecnicoService.get_pending_fsas(self.tecnico.id)
        return self._pending_fsas

    def __getattr__(self, name):
        """Proxy para atributos do tecnico ORM."""
        return getattr(self.tecnico, name)

# Validation Schema
class TecnicoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    nome = fields.Str(required=True, validate=validate.Length(min=3))
    documento = fields.Str(allow_none=True)
    contato = fields.Str(required=True)
    cep = fields.Str(allow_none=True)  # CEP
    logradouro = fields.Str(allow_none=True)  # Rua, Av...
    numero = fields.Str(allow_none=True)  # Número do endereço
    complemento = fields.Str(allow_none=True)  # Apt, sala, etc
    bairro = fields.Str(allow_none=True)  # Bairro
    cidade = fields.Str(required=True)
    estado = fields.Str(required=True, validate=validate.Length(equal=2))
    observacoes = fields.Str(allow_none=True)  # Notas sobre o técnico
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

    # ==========================================================================
    # CONDICOES SQL REUTILIZAVEIS (DRY)
    # ==========================================================================

    @staticmethod
    def _chamado_pendente_condition():
        """Condicao SQL para chamados pendentes de pagamento."""
        return and_(
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.status_validacao == 'Aprovado',
            Chamado.pago == False,
            Chamado.pagamento_id == None
        )

    @staticmethod
    def _valor_chamado_expr():
        """Expressao SQL para valor do chamado (custo_atribuido)."""
        # REFATORADO: Removido fallback para Chamado.valor (campo DEPRECATED)
        return func.coalesce(Chamado.custo_atribuido, 0)

    # ==========================================================================
    # METODO PRINCIPAL: GET TECNICOS COM METRICAS (UMA UNICA QUERY SQL)
    # ==========================================================================

    @staticmethod
    def get_tecnicos_com_metricas(
        filters: Optional[Dict] = None,
        page: int = 1,
        per_page: int = 20,
        include_subs: bool = True
    ) -> Dict[str, Any]:
        """
        Busca tecnicos com TODAS as metricas agregadas em UMA UNICA query SQL.
        Resolve o problema N+1 de forma definitiva.

        Args:
            filters: Filtros (search, estado, pagamento, status)
            page: Pagina atual (None para todos)
            per_page: Itens por pagina
            include_subs: Se True, calcula totais de sub-tecnicos

        Returns:
            Dict com 'items' (lista de TecnicoMetricas), 'pagination' e metadados
        """
        val_expr = TecnicoService._valor_chamado_expr()
        pend_cond = TecnicoService._chamado_pendente_condition()

        # ======================================================================
        # AGREGACOES SQL (Tudo em uma query)
        # ======================================================================

        # Total de atendimentos
        total_atendimentos = func.count(Chamado.id).label('total_atendimentos')

        # Total concluidos
        total_concluidos = func.sum(
            case(
                (Chamado.status_chamado.in_(['Concluído', 'SPARE']), 1),
                else_=0
            )
        ).label('total_concluidos')

        # Total nao pagos
        # Total nao pagos (VALIDADOS E PENDENTES DE PAGAMENTO)
        total_nao_pagos = func.sum(
            case(
                (pend_cond, 1),
                else_=0
            )
        ).label('total_nao_pagos')

        # Valor pendente de pagamento
        valor_pendente = func.sum(
            case(
                (pend_cond, val_expr),
                else_=0
            )
        ).label('total_pendente')

        # Data mais antiga de chamado pendente
        oldest_pending = func.min(
            case(
                (pend_cond, Chamado.data_atendimento),
                else_=None
            )
        ).label('oldest_pending')

        # Data mais recente de chamado pendente
        newest_pending = func.max(
            case(
                (pend_cond, Chamado.data_atendimento),
                else_=None
            )
        ).label('newest_pending')

        # ======================================================================
        # QUERY PRINCIPAL
        # ======================================================================

        query = db.session.query(
            Tecnico,
            total_atendimentos,
            total_concluidos,
            total_nao_pagos,
            valor_pendente,
            oldest_pending,
            newest_pending
        ).outerjoin(
            Chamado, Tecnico.id == Chamado.tecnico_id
        ).group_by(Tecnico.id)

        # ======================================================================
        # FILTROS
        # ======================================================================

        if filters:
            if filters.get('search'):
                term = f"%{filters['search']}%"
                query = query.filter(
                    or_(
                        Tecnico.nome.ilike(term),
                        Tecnico.cidade.ilike(term),
                        Tecnico.documento.ilike(term)
                    )
                )

            if filters.get('estado'):
                query = query.filter(Tecnico.estado == filters['estado'])

            if filters.get('status'):
                query = query.filter(Tecnico.status == filters['status'])

            # Filtro por status de pagamento (HAVING pos-agregacao)
            if filters.get('pagamento') == 'Pendente':
                query = query.having(valor_pendente > 0)
            elif filters.get('pagamento') == 'Pago':
                query = query.having(func.coalesce(valor_pendente, 0) == 0)

        # Ordenacao
        query = query.order_by(Tecnico.nome)

        # ======================================================================
        # PAGINACAO OU TODOS
        # ======================================================================

        if page is None:
            # Retorna todos (sem paginacao)
            results = query.all()
            pagination_info = None
        else:
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            results = pagination.items
            pagination_info = {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
                'next_num': pagination.next_num,
                'prev_num': pagination.prev_num
            }

        # ======================================================================
        # CALCULAR VALORES DE SUB-TECNICOS (Segunda query otimizada)
        # ======================================================================

        subs_totals = {}
        if include_subs:
            # Busca soma de pendentes agrupada por tecnico_principal_id
            sub_query = db.session.query(
                Tecnico.tecnico_principal_id,
                func.sum(
                    case(
                        (pend_cond, val_expr),
                        else_=0
                    )
                ).label('sub_total')
            ).join(
                Chamado, Tecnico.id == Chamado.tecnico_id
            ).filter(
                Tecnico.tecnico_principal_id != None
            ).group_by(
                Tecnico.tecnico_principal_id
            ).all()

            subs_totals = {row[0]: float(row[1] or 0) for row in sub_query}

        # ======================================================================
        # MONTAR OBJETOS TecnicoMetricas
        # ======================================================================

        items = []
        for row in results:
            tecnico = row[0]
            metricas = TecnicoMetricas(
                tecnico=tecnico,
                total_atendimentos=int(row[1] or 0),
                total_atendimentos_concluidos=int(row[2] or 0),
                total_atendimentos_nao_pagos=int(row[3] or 0),
                total_a_pagar=float(row[4] or 0),
                total_a_pagar_subs=subs_totals.get(tecnico.id, 0.0),
                oldest_pending_date=row[5],
                newest_pending_date=row[6]
            )

            # Injetar cache no objeto ORM para compatibilidade com codigo legado
            tecnico.total_a_pagar_cache = metricas.total_a_pagar_agregado
            tecnico._metricas = metricas

            items.append(metricas)

        return {
            'items': items,
            'pagination': pagination_info,
            'total_count': len(items) if page is None else pagination_info['total']
        }

    # ==========================================================================
    # METODO LEGADO REFATORADO (Mantido para compatibilidade)
    # ==========================================================================

    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        """
        Metodo legado mantido para compatibilidade.
        INTERNAMENTE usa get_tecnicos_com_metricas().

        Retorna objeto de paginacao com items sendo objetos Tecnico
        (com total_a_pagar_cache injetado).
        """
        result = TecnicoService.get_tecnicos_com_metricas(
            filters=filters,
            page=page,
            per_page=per_page
        )

        # Se nao paginado, retorna lista de Tecnicos diretamente
        if page is None:
            return [m.tecnico for m in result['items']]

        # Criar objeto de paginacao compativel
        class PaginationCompat:
            """Wrapper para manter compatibilidade com codigo existente."""
            def __init__(self, data):
                self.items = [m.tecnico for m in data['items']]
                p = data['pagination']
                self.page = p['page']
                self.per_page = p['per_page']
                self.total = p['total']
                self.pages = p['pages']
                self.has_next = p['has_next']
                self.has_prev = p['has_prev']
                self.next_num = p['next_num']
                self.prev_num = p['prev_num']

            def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
                """Gera numeros de pagina para navegacao."""
                last = 0
                for num in range(1, self.pages + 1):
                    if (num <= left_edge or
                        (self.page - left_current - 1 < num < self.page + right_current) or
                        num > self.pages - right_edge):
                        if last + 1 != num:
                            yield None
                        yield num
                        last = num

        return PaginationCompat(result)

    @staticmethod
    def get_by_id(id):
        """
        Busca tecnico por ID com metricas calculadas via SQL.
        REFATORADO: Usa query otimizada em vez de N+1.
        """
        tecnico = Tecnico.query.options(joinedload(Tecnico.tags)).get_or_404(id)

        # Calcular metricas via SQL otimizado
        metricas = TecnicoService.calcular_saldo_pendente(id)

        # Injetar no objeto para compatibilidade
        tecnico.total_a_pagar_cache = metricas['total_a_pagar']
        tecnico._total_agregado_cache = metricas['total_agregado']  # Use private attr (property uses this)
        tecnico._metricas_detalhe = metricas

        return tecnico

    @staticmethod
    def calcular_saldo_pendente(tecnico_id: int) -> Dict[str, Any]:
        """
        Calcula saldo pendente de um tecnico usando SQL otimizado.
        Inclui valores de sub-tecnicos se aplicavel.

        Args:
            tecnico_id: ID do tecnico

        Returns:
            Dict com total_a_pagar, total_agregado, contagens, etc.
        """
        val_expr = TecnicoService._valor_chamado_expr()
        pend_cond = TecnicoService._chamado_pendente_condition()

        # Query para o proprio tecnico
        own_result = db.session.query(
            func.sum(case((pend_cond, val_expr), else_=0)).label('valor'),
            func.sum(case((pend_cond, 1), else_=0)).label('count'),
            func.min(case((pend_cond, Chamado.data_atendimento), else_=None)).label('oldest'),
            func.max(case((pend_cond, Chamado.data_atendimento), else_=None)).label('newest')
        ).filter(
            Chamado.tecnico_id == tecnico_id
        ).first()

        own_val = float(own_result[0] or 0)
        own_cnt = int(own_result[1] or 0)
        oldest = own_result[2]
        newest = own_result[3]

        # Query para sub-tecnicos (uma unica query)
        sub_result = db.session.query(
            func.sum(case((pend_cond, val_expr), else_=0)).label('valor'),
            func.sum(case((pend_cond, 1), else_=0)).label('count')
        ).join(
            Tecnico, Chamado.tecnico_id == Tecnico.id
        ).filter(
            Tecnico.tecnico_principal_id == tecnico_id
        ).first()

        sub_val = float(sub_result[0] or 0)
        sub_cnt = int(sub_result[1] or 0)

        return {
            'total_a_pagar': own_val,
            'total_a_pagar_subs': sub_val,
            'total_agregado': own_val + sub_val,
            'count_pendentes': own_cnt,
            'count_pendentes_subs': sub_cnt,
            'count_total': own_cnt + sub_cnt,
            'oldest_pending_date': oldest,
            'newest_pending_date': newest
        }

    @staticmethod
    def create(data):
        try:
            val_data = tecnico_schema.load(data)
        except ValidationError as err:
            raise ValueError(f"Erro de validação: {err.messages}")

        tecnico = Tecnico(**val_data)
        db.session.add(tecnico)
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
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
            
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return tecnico

    @staticmethod
    def delete(id, user_id):
        tecnico = TecnicoService.get_by_id(id)
        
        # Security Check: Dependencies
        if tecnico.pagamentos.count() > 0:
            raise ValueError("Este técnico possui histórico de pagamentos. Use a opção 'Inativar' em vez de excluir.")
            
        if tecnico.chamados.count() > 0:
             raise ValueError("Este técnico possui chamados vinculados. Reatribua os chamados ou use 'Inativar'.")

        # Check: Sub-Tecnicos
        if tecnico.sub_tecnicos:
             raise ValueError("Este técnico possui sub-técnicos vinculados. Desvincule-os antes de excluir.")

        # Check: Stock (Block if has items, delete if empty)
        if tecnico.estoque:
            if any(item.quantidade > 0 for item in tecnico.estoque):
                raise ValueError("Este técnico possui estoque. Realize a devolução dos itens antes de excluir.")
            # Cleanup zero-quantity stock records to avoid IntegrityError
            for item in tecnico.estoque:
                db.session.delete(item)

        # Check: Solicitations (History)
        if tecnico.solicitacoes_reposicao:
             raise ValueError("Este técnico possui histórico de solicitações de reposição. Use 'Inativar'.")

        # Audit
        from .audit_service import AuditService
        AuditService.log_change(
            model_name='Tecnico',
            object_id=tecnico.id,
            action='DELETE',
            changes=f"Deleted Tecnico {tecnico.nome} (ID: {tecnico.id_tecnico})"
        )
        
        db.session.delete(tecnico)
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar

    @staticmethod
    def get_stats():
        """Estatisticas gerais de tecnicos usando query otimizada."""
        val_expr = TecnicoService._valor_chamado_expr()
        pend_cond = TecnicoService._chamado_pendente_condition()

        total_pendente = db.session.query(
            func.sum(case((pend_cond, val_expr), else_=0))
        ).scalar() or 0.0

        return {
            'ativos': Tecnico.query.filter_by(status='Ativo').count(),
            'total_pendente': float(total_pendente)
        }

    @staticmethod
    def get_pendencias(tecnico_id: int) -> List[Any]:
        """
        Busca chamados pendentes de um tecnico (incluindo sub-tecnicos).
        Query otimizada que substitui a @property deprecated.
        """
        pend_cond = TecnicoService._chamado_pendente_condition()

        # IDs do tecnico e seus sub-tecnicos
        tecnico = Tecnico.query.get_or_404(tecnico_id)
        sub_ids = [s.id for s in tecnico.sub_tecnicos]
        all_ids = [tecnico_id] + sub_ids

        # Query unica para todos os chamados pendentes
        chamados = Chamado.query.filter(
            Chamado.tecnico_id.in_(all_ids),
            pend_cond
        ).order_by(Chamado.data_atendimento.desc()).all()

        return chamados

    @staticmethod
    def get_pending_fsas(tecnico_id: int) -> List[str]:
        """
        Busca codigos FSA de chamados pendentes.
        Substitui a @property pending_fsas do Model.
        """
        chamados = TecnicoService.get_pendencias(tecnico_id)

        codes = []
        for c in chamados:
            if c.codigo_chamado:
                codes.append(c.codigo_chamado)
            if c.fsa_codes:
                extras = [x.strip() for x in c.fsa_codes.replace(';', ',').split(',') if x.strip()]
                codes.extend(extras)

        return sorted(list(set(codes)))
