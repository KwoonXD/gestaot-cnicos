from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from decimal import Decimal

# Utilitários de serialização monetária
from .utils.serialization import money_str, to_decimal

db = SQLAlchemy()

ESTADOS_BRASIL = [
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
    'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC',
    'SP', 'SE', 'TO'
]

FORMAS_PAGAMENTO = ['PIX', 'Transferência Bancária', 'Boleto', 'Dinheiro']

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Operador') 
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role in ['Admin', 'Financeiro']

class Tecnico(db.Model):
    __tablename__ = 'tecnicos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    documento = db.Column(db.String(20), unique=True, nullable=True) # CPF/CNPJ
    contato = db.Column(db.String(20), nullable=False)
    cep = db.Column(db.String(10), nullable=True)  # CEP (00000-000)
    logradouro = db.Column(db.String(200), nullable=True)  # Rua, Av...
    numero = db.Column(db.String(20), nullable=True)  # Número do endereço
    complemento = db.Column(db.String(100), nullable=True)  # Apt, sala, etc
    bairro = db.Column(db.String(100), nullable=True)  # Bairro
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)  # Notas sobre o técnico
    status = db.Column(db.String(20), default='Ativo')
    valor_por_atendimento = db.Column(db.Numeric(10, 2), default=120.00)
    valor_adicional_loja = db.Column(db.Numeric(10, 2), default=20.00)
    valor_hora_adicional = db.Column(db.Numeric(10, 2), default=30.00)  # Valor por hora extra
    forma_pagamento = db.Column(db.String(50), nullable=True)
    chave_pagamento = db.Column(db.String(200), nullable=True)
    tecnico_principal_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=True)

    token_acesso = db.Column(db.String(36), unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    data_inicio = db.Column(db.Date, nullable=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    
    tecnico_principal = db.relationship('Tecnico', remote_side=[id], backref='sub_tecnicos', foreign_keys=[tecnico_principal_id])
    chamados = db.relationship('Chamado', backref='tecnico', lazy='dynamic', foreign_keys='Chamado.tecnico_id')
    pagamentos = db.relationship('Pagamento', backref='tecnico', lazy='dynamic')
    tags = db.relationship('Tag', backref='tecnico')
    
    # ==========================================================================
    # PROPRIEDADES SIMPLES (Sem query - OK para uso em loops)
    # ==========================================================================

    @property
    def id_tecnico(self):
        return f"T-{str(self.id).zfill(3)}"

    @property
    def localizacao(self):
        return f"{self.cidade}/{self.estado}"

    @property
    def identificacao_completa(self):
        return f"[{self.id_tecnico}] {self.nome} - {self.localizacao}"

    # ==========================================================================
    # PROPRIEDADES AGREGADAS (SOMENTE VIA CACHE - SEM QUERIES)
    # OBRIGATORIO: Use TecnicoService.get_tecnicos_com_metricas() para popular
    # ==========================================================================

    @property
    def total_atendimentos(self):
        """
        REFATORADO (2025): Retorna APENAS cache, sem fallback para query.
        Use TecnicoService.get_tecnicos_com_metricas() ANTES de acessar.
        """
        if hasattr(self, '_metricas'):
            return self._metricas.total_atendimentos
        if hasattr(self, '_metricas_detalhe'):
            return self._metricas_detalhe.get('count_total', 0)
        # Sem fallback - retorna 0 e emite aviso
        import warnings
        warnings.warn(
            f"Tecnico {self.id}.total_atendimentos acessado sem cache. "
            "Use TecnicoService.get_tecnicos_com_metricas() primeiro.",
            DeprecationWarning, stacklevel=2
        )
        return 0

    @property
    def total_atendimentos_concluidos(self):
        """
        REFATORADO (2025): Retorna APENAS cache, sem fallback para query.
        """
        if hasattr(self, '_metricas'):
            return self._metricas.total_atendimentos_concluidos
        import warnings
        warnings.warn(
            f"Tecnico {self.id}.total_atendimentos_concluidos acessado sem cache.",
            DeprecationWarning, stacklevel=2
        )
        return 0

    @property
    def total_atendimentos_nao_pagos(self):
        """
        REFATORADO (2025): Retorna APENAS cache, sem fallback para query.
        """
        if hasattr(self, '_metricas'):
            return self._metricas.total_atendimentos_nao_pagos
        if hasattr(self, '_metricas_detalhe'):
            return self._metricas_detalhe.get('count_pendentes', 0)
        import warnings
        warnings.warn(
            f"Tecnico {self.id}.total_atendimentos_nao_pagos acessado sem cache.",
            DeprecationWarning, stacklevel=2
        )
        return 0

    @property
    def total_a_pagar(self):
        """
        REFATORADO (2025): Retorna APENAS cache, sem fallback para query.
        Elimina imports locais e queries dentro do Model.

        OBRIGATORIO: Usar TecnicoService.get_by_id() ou get_tecnicos_com_metricas()
        para popular o cache ANTES de acessar esta property.
        """
        # 1. Cache injetado pelo Service (preferido)
        if hasattr(self, 'total_a_pagar_cache'):
            return self.total_a_pagar_cache

        # 2. Metricas pre-calculadas
        if hasattr(self, '_metricas'):
            return self._metricas.total_a_pagar

        # 3. Metricas detalhe (de get_by_id)
        if hasattr(self, '_metricas_detalhe'):
            return self._metricas_detalhe.get('total_a_pagar', 0.0)

        # 4. SEM FALLBACK - emite aviso e retorna 0
        import warnings
        warnings.warn(
            f"Tecnico {self.id}.total_a_pagar acessado SEM cache pre-calculado. "
            "OBRIGATORIO: Use TecnicoService.get_by_id() ou get_tecnicos_com_metricas() "
            "para popular metricas ANTES de acessar. Retornando 0.",
            DeprecationWarning, stacklevel=2
        )
        return 0.0

    @property
    def total_agregado(self):
        """
        Total incluindo sub-tecnicos. Alias para compatibilidade.
        REFATORADO (2025): Retorna APENAS cache.
        """
        # Verifica atributo privado (nao a property)
        if hasattr(self, '_total_agregado_cache'):
            return self._total_agregado_cache
        if hasattr(self, '_metricas'):
            return self._metricas.total_a_pagar_agregado
        if hasattr(self, '_metricas_detalhe'):
            return self._metricas_detalhe.get('total_agregado', 0.0)
        return self.total_a_pagar  # Fallback para total simples

    @property
    def status_pagamento(self):
        """Derivado de total_a_pagar (usa cache se disponivel)."""
        return "Pendente" if self.total_a_pagar > 0 else "Pago"

    # ==========================================================================
    # PROPRIEDADES REMOVIDAS/DEPRECATED (Causavam N+1 grave)
    # Usar TecnicoService.get_pendencias() em vez disso
    # ==========================================================================

    @property
    def pending_chamados_list(self):
        """
        DEPRECATED: Causa N+1 queries em loops.
        Use TecnicoService.get_pendencias(tecnico_id) em vez disso.
        """
        import warnings
        warnings.warn(
            "pending_chamados_list e deprecated. Use TecnicoService.get_pendencias()",
            DeprecationWarning,
            stacklevel=2
        )
        if self.tecnico_principal_id:
            return []

        chamados = list(self.chamados.filter(
            Chamado.status_chamado.in_(['Concluído', 'SPARE']),
            Chamado.status_validacao == 'Aprovado',
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ))
        for sub in self.sub_tecnicos:
            chamados.extend(list(sub.chamados.filter(
                Chamado.status_chamado.in_(['Concluído', 'SPARE']),
                Chamado.status_validacao == 'Aprovado',
                Chamado.pago == False,
                Chamado.pagamento_id == None
            )))
        return chamados

    @property
    def pending_fsas(self):
        """
        DEPRECATED: Depende de pending_chamados_list.
        Use TecnicoService.get_pending_fsas(tecnico_id) em vez disso.
        """
        codes = []
        for c in self.pending_chamados_list:
            if c.codigo_chamado:
                codes.append(c.codigo_chamado)
            if c.fsa_codes:
                extras = [x.strip() for x in c.fsa_codes.replace(';', ',').split(',') if x.strip()]
                codes.extend(extras)
        return sorted(list(set(codes)))

    @property
    def oldest_pending_atendimento(self):
        """
        DEPRECATED em loops: Use metricas do Service.
        """
        if hasattr(self, '_metricas') and self._metricas.oldest_pending_date:
            return self._metricas.oldest_pending_date
        if hasattr(self, '_metricas_detalhe') and self._metricas_detalhe.get('oldest_pending_date'):
            return self._metricas_detalhe['oldest_pending_date']
        # Fallback
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_atendimento for c in chamados if c.data_atendimento]
        return min(dates) if dates else None

    @property
    def oldest_pending_criacao(self):
        """DEPRECATED: Use metricas do Service."""
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_criacao for c in chamados if c.data_criacao]
        return min(dates) if dates else None

    @property
    def newest_pending_atendimento(self):
        """DEPRECATED em loops: Use metricas do Service."""
        if hasattr(self, '_metricas') and self._metricas.newest_pending_date:
            return self._metricas.newest_pending_date
        if hasattr(self, '_metricas_detalhe') and self._metricas_detalhe.get('newest_pending_date'):
            return self._metricas_detalhe['newest_pending_date']
        # Fallback
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_atendimento for c in chamados if c.data_atendimento]
        return max(dates) if dates else None

    @property
    def newest_pending_criacao(self):
        """DEPRECATED: Use metricas do Service."""
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_criacao for c in chamados if c.data_criacao]
        return max(dates) if dates else None

    # ==========================================================================
    # SERIALIZACAO
    # ==========================================================================

    def to_dict(self, include_heavy=False):
        """
        Serializa tecnico para dict.

        Args:
            include_heavy: Se True, inclui campos que podem causar queries.
                          Use apenas para tecnico individual, nunca em listas.
        """
        data = {
            'id': self.id,
            'id_tecnico': self.id_tecnico,
            'nome': self.nome,
            'contato': self.contato,
            'cidade': self.cidade,
            'estado': self.estado,
            'localizacao': self.localizacao,
            'status': self.status,
            # Valores monetários serializados como string para preservar precisão
            'valor_por_atendimento': money_str(self.valor_por_atendimento),
            'valor_adicional_loja': money_str(self.valor_adicional_loja),
            'valor_hora_adicional': money_str(self.valor_hora_adicional),
            'forma_pagamento': self.forma_pagamento,
            'chave_pagamento': self.chave_pagamento,
            'tecnico_principal_id': self.tecnico_principal_id,
            'tecnico_principal_nome': self.tecnico_principal.nome if self.tecnico_principal else None,
            'data_inicio': self.data_inicio.isoformat() if self.data_inicio else None,
            'data_cadastro': self.data_cadastro.isoformat() if self.data_cadastro else None,
            'tags': [t.to_dict() for t in self.tags]
        }

        # Campos agregados (apenas se cache disponivel ou solicitado)
        if include_heavy or hasattr(self, 'total_a_pagar_cache') or hasattr(self, '_metricas'):
            data.update({
                'total_atendimentos': self.total_atendimentos,
                'total_atendimentos_concluidos': self.total_atendimentos_concluidos,
                'total_atendimentos_nao_pagos': self.total_atendimentos_nao_pagos,
                'total_a_pagar': self.total_a_pagar,
                'status_pagamento': self.status_pagamento,
            })

        return data


class Chamado(db.Model):
    __tablename__ = 'chamados'
    
    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    codigo_chamado = db.Column(db.String(100), nullable=True)
    cidade = db.Column(db.String(100), nullable=False, default='Indefinido')
    loja = db.Column(db.String(100), nullable=True)
    data_atendimento = db.Column(db.Date, nullable=False)
    
    # Serviço (Novo modelo unificado)
    catalogo_servico_id = db.Column(db.Integer, db.ForeignKey('catalogo_servicos.id'), nullable=True)
    catalogo_servico = db.relationship('CatalogoServico', foreign_keys=[catalogo_servico_id])
    
    # Campos legados (mantidos para compatibilidade)
    # Campos legados (mantidos para compatibilidade)
    # tipo_servico = db.Column(db.String(50), nullable=True)
    # tipo_resolucao = db.Column(db.String(50), default='')
    
    @property
    def servico_nome(self):
        if self.catalogo_servico:
            return self.catalogo_servico.nome
        return "Serviço Removido"

    # Compatibility Aliases (Prevent AttributeError in legacy code)
    @property
    def tipo_servico(self):
        return self.servico_nome
        
    @property
    def tipo_resolucao(self):
        return self.servico_nome # Fallback to service name or empty string
    
    status_chamado = db.Column(db.String(20), default='Concluído')
    is_adicional = db.Column(db.Boolean, default=False)
    
    # Horas Trabalhadas (Entrada: hora_inicio/hora_fim, Calculado: horas_trabalhadas)
    hora_inicio = db.Column(db.String(5), nullable=True)  # Ex: "09:00"
    hora_fim = db.Column(db.String(5), nullable=True)      # Ex: "12:30"
    horas_trabalhadas = db.Column(db.Float, default=2.0)   # Calculado automaticamente
    valor_horas_extras = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Financeiro - RECEITA
    valor_receita_total = db.Column(db.Numeric(10, 2), default=0.00)
    valor_receita_servico = db.Column(db.Numeric(10, 2), default=0.00)
    peca_usada = db.Column(db.String(100), nullable=True)
    valor_receita_peca = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Financeiro - CUSTO
    custo_peca = db.Column(db.Numeric(10, 2), default=0.00)
    fornecedor_peca = db.Column(db.String(20), default='Empresa')
    custo_atribuido = db.Column(db.Numeric(10, 2), default=0.00)

    # DEPRECATED: Este campo sera removido em versao futura.
    # Use 'custo_atribuido' para custos. Mantido apenas para compatibilidade.
    # Data de deprecacao: 2026-01-12 | Previsao de remocao: 2026-03-14
    # Fase 1 (2026-01-14): Tornado nullable
    # Fase 2 (2026-02-14): Remover de to_dict() e APIs
    # Fase 3 (2026-03-14): DROP COLUMN
    valor = db.Column(db.Numeric(10, 2), nullable=True, default=0.00)
    pago = db.Column(db.Boolean, default=False)
    pagamento_id = db.Column(db.Integer, db.ForeignKey('pagamentos.id'), nullable=True)
    endereco = db.Column(db.Text, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    fsa_codes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Agrupamento por Lote/Atendimento
    batch_id = db.Column(db.String(36), index=True, nullable=True)  # UUID para vincular FSAs do mesmo atendimento
    
    # Workflow de Validação
    status_validacao = db.Column(db.String(20), default='Pendente')  # 'Pendente', 'Aprovado', 'Rejeitado'
    data_validacao = db.Column(db.DateTime, nullable=True)
    validado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    validado_por = db.relationship('User', foreign_keys=[validado_por_id])
    
    # Campos de Rejeição (Soft Delete)
    motivo_rejeicao = db.Column(db.Text, nullable=True)
    data_rejeicao = db.Column(db.DateTime, nullable=True)
    rejeitado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rejeitado_por = db.relationship('User', foreign_keys=[rejeitado_por_id])
    
    # Rastreabilidade
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    
    @property
    def id_chamado(self):
        year = self.data_atendimento.year if self.data_atendimento else datetime.now().year
        return f"CHAM-{year}-{str(self.id).zfill(4)}"
    
    @property
    def localizacao(self):
        return self.tecnico.localizacao if self.tecnico else None
    
    def to_dict(self):
        """
        Serializa chamado para dict.
        
        NOTA: Valores monetarios sao serializados como string com 2 casas
        decimais para preservar precisao (evita arredondamento de float).
        
        Campo 'valor' esta DEPRECATED - usar 'custo_atribuido'
        """
        from decimal import Decimal, ROUND_HALF_UP
        TWO_PLACES = Decimal('0.01')
        
        def format_money(value):
            """Formata valor monetario como string com 2 casas decimais."""
            if value is None:
                return '0.00'
            if isinstance(value, Decimal):
                return str(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))
            return str(Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))
        
        return {
            'id': self.id,
            'id_chamado': self.id_chamado,
            'codigo_chamado': self.codigo_chamado,
            'tecnico_id': self.tecnico_id,
            'tecnico_nome': self.tecnico.nome if self.tecnico else None,
            'tecnico_id_formatado': self.tecnico.id_tecnico if self.tecnico else None,
            'data_atendimento': self.data_atendimento.isoformat() if self.data_atendimento else None,
            'tipo_servico': self.tipo_servico,
            'status_chamado': self.status_chamado,
            'pago': self.pago,
            'pagamento_id': self.pagamento_id,
            'endereco': self.endereco,
            'observacoes': self.observacoes,
            'localizacao': self.localizacao,
            # Campo preferido para custos (string para preservar precisão)
            'custo_atribuido': format_money(self.custo_atribuido),
            # DEPRECATED: Campo 'valor' sera removido em 2026-03-14
            # Mantido apenas para compatibilidade com integrações existentes
            'valor': format_money(self.valor),
            '_deprecated_fields': ['valor'],  # Sinal para consumidores de API
            'data_criacao': self.data_criacao.isoformat() if self.data_criacao else None
        }


class Pagamento(db.Model):
    __tablename__ = 'pagamentos'
    
    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    valor_por_atendimento = db.Column(db.Numeric(10, 2), nullable=False)
    status_pagamento = db.Column(db.String(20), default='Pendente')
    data_pagamento = db.Column(db.Date, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    comprovante_path = db.Column(db.String(255), nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    chamados_incluidos = db.relationship('Chamado', backref='pagamento', lazy='dynamic')
    
    @property
    def id_pagamento(self):
        year = self.periodo_fim.year if self.periodo_fim else datetime.now().year
        month = str(self.periodo_fim.month).zfill(2) if self.periodo_fim else '01'
        tecnico_id = self.tecnico.id_tecnico if self.tecnico else 'T-000'
        return f"PAG-{tecnico_id}-{year}{month}"
    
    @property
    def numero_chamados(self):
        return self.chamados_incluidos.count()
    
    @property
    def valor_total(self):
        # REFATORADO: Usando apenas custo_atribuido (campo valor está DEPRECATED)
        # Retorna Decimal para preservar precisão
        from decimal import Decimal
        return sum((c.custo_atribuido or Decimal('0.00')) for c in self.chamados_incluidos)
    
    def to_dict(self):
        return {
            'id': self.id,
            'id_pagamento': self.id_pagamento,
            'tecnico_id': self.tecnico_id,
            'tecnico_nome': self.tecnico.nome if self.tecnico else None,
            'tecnico_id_formatado': self.tecnico.id_tecnico if self.tecnico else None,
            'periodo_inicio': self.periodo_inicio.isoformat() if self.periodo_inicio else None,
            'periodo_fim': self.periodo_fim.isoformat() if self.periodo_fim else None,
            'numero_chamados': self.numero_chamados,
            'valor_por_atendimento': money_str(self.valor_por_atendimento),
            'valor_total': money_str(self.valor_total),
            'status_pagamento': self.status_pagamento,
            'data_pagamento': self.data_pagamento.isoformat() if self.data_pagamento else None,
            'observacoes': self.observacoes,
            'data_criacao': self.data_criacao.isoformat() if self.data_criacao else None
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    model_name = db.Column(db.String(50), nullable=False)
    object_id = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    changes = db.Column(db.Text, nullable=True)  # JSON string of changes
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='audi_logs')




class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    cor = db.Column(db.String(7), nullable=False)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'cor': self.cor,
            'tecnico_id': self.tecnico_id
        }

class SavedView(db.Model):
    __tablename__ = 'saved_views'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    page_route = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    query_string = db.Column(db.Text, nullable=False)
    
    user = db.relationship('User', backref='saved_views')


# =============================================================================
# GESTÃO DE CONTRATOS (Motor de Regras Dinâmicas)
# =============================================================================

class Cliente(db.Model):
    """Cliente/Contrato - Ex: Americanas, Raia Drogasil"""
    __tablename__ = 'clientes'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    tipos_servico = db.relationship('CatalogoServico', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    itens_lpu = db.relationship('ItemLPU', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    # Tabela de precos personalizada (ContratoItem)
    itens = db.relationship('ContratoItem', backref='contrato', lazy='dynamic', foreign_keys='ContratoItem.cliente_id', overlaps='cliente,itens_contrato')

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'ativo': self.ativo,
            'servicos': [s.to_dict() for s in self.tipos_servico],
            'lpu': [l.to_dict() for l in self.itens_lpu]
        }


class JobRun(db.Model):
    """
    Registro de execução de tarefas em background (Auditoria).
    Usado para monitorar o processamento financeiro em lote.
    """
    __tablename__ = 'job_runs'

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(50), nullable=False) # ex: 'financeiro_lote'
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='RUNNING') # RUNNING, COMPLETED, FAILED, PARTIAL
    
    # Métricas
    total_items = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    
    # Detalhes (JSON ou Texto)
    log_text = db.Column(db.Text, nullable=True) # Logs importantes/Erros
    metadata_json = db.Column(db.Text, nullable=True) # Params de entrada (periodo, etc)

    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else None,
            'status': self.status,
            'total_items': self.total_items,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'log_text': self.log_text
        }



class CatalogoServico(db.Model):
    """
    Catálogo Unificado de Serviços por Cliente.
    Une 'Tipo de Serviço' e 'Resolução' em uma única entidade com regras de negócio.
    """
    __tablename__ = 'catalogo_servicos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)  # Ex: "Zebra - 1ª Visita", "Retorno SPARE"
    valor_receita = db.Column(db.Numeric(10, 2), default=0.0)  # Receita para a empresa (R$)
    valor_custo_tecnico = db.Column(db.Numeric(10, 2), default=0.0) # Custo (quanto paga ao técnico)
    
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    
    # Regras de Negócio
    exige_peca = db.Column(db.Boolean, default=False)     # Se True, mostra seleção de LPU
    paga_tecnico = db.Column(db.Boolean, default=True)    # Se False (ex: Falha), técnico recebe 0
    pagamento_integral = db.Column(db.Boolean, default=False) # Se True (ex: Retorno SPARE), não aplica regra de lote (sempre valor cheio)
    is_retorno = db.Column(db.Boolean, default=False)     # Novo campo para identificar retornos
    horas_franquia = db.Column(db.Integer, default=2)     # Até quantas horas o valor base cobre
    
    # Valores Adicionais (para chamados extras no mesmo lote)
    valor_adicional_receita = db.Column(db.Numeric(10, 2), default=0.0)
    valor_adicional_custo = db.Column(db.Numeric(10, 2), default=0.0)

    # Horas Extras
    valor_hora_adicional_receita = db.Column(db.Numeric(10, 2), default=0.0)
    valor_hora_adicional_custo = db.Column(db.Numeric(10, 2), default=0.0)
    
    # Status
    ativo = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            # Valores monetários serializados via money_str para garantir 2 casas
            'valor': money_str(self.valor_receita),
            'valor_custo_tecnico': money_str(self.valor_custo_tecnico),
            'exige_peca': self.exige_peca,
            'paga_tecnico': self.paga_tecnico,
            'pagamento_integral': self.pagamento_integral,
            'horas_franquia': self.horas_franquia,
            'valor_adicional_receita': money_str(self.valor_adicional_receita),
            'valor_adicional_custo': money_str(self.valor_adicional_custo),
            'valor_hora_adicional_receita': money_str(self.valor_hora_adicional_receita),
            'valor_hora_adicional_custo': money_str(self.valor_hora_adicional_custo),
            'is_retorno': self.is_retorno
        }


# Alias para compatibilidade com código existente
TipoServico = CatalogoServico


class ItemLPU(db.Model):
    """Itens LPU (Peças) por Cliente - Ex: Scanner (R$ 180), Monitor (R$ 200)"""
    __tablename__ = 'itens_lpu'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor_receita = db.Column(db.Numeric(10, 2), default=0.0)  # Preço cobrado do cliente
    valor_custo = db.Column(db.Numeric(10, 2), default=0.0)    # Custo de aquisição da peça
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)

    @property
    def margem(self):
        """Margem bruta da peça (receita - custo)"""
        return to_decimal(self.valor_receita) - to_decimal(self.valor_custo)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            # Valores monetários serializados via money_str
            'valor': money_str(self.valor_receita),
            'valor_custo': money_str(self.valor_custo),
            'margem': money_str(self.margem)
        }


class ItemLPUPrecoHistorico(db.Model):
    """Histórico de alterações de preços de peças (custo e receita)"""
    __tablename__ = 'itens_lpu_preco_historico'

    id = db.Column(db.Integer, primary_key=True)
    item_lpu_id = db.Column(db.Integer, db.ForeignKey('itens_lpu.id'), nullable=False, index=True)

    # Valores ANTES da alteração
    valor_custo_anterior = db.Column(db.Numeric(10, 2), nullable=True)
    valor_receita_anterior = db.Column(db.Numeric(10, 2), nullable=True)

    # Valores DEPOIS da alteração
    valor_custo_novo = db.Column(db.Numeric(10, 2), nullable=True)
    valor_receita_novo = db.Column(db.Numeric(10, 2), nullable=True)

    # Metadados
    motivo = db.Column(db.String(200), nullable=True)  # Motivo da alteração
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow)
    alterado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relacionamentos
    item_lpu = db.relationship('ItemLPU', backref=db.backref('historico_precos', lazy='dynamic', order_by='ItemLPUPrecoHistorico.data_alteracao.desc()'))
    alterado_por = db.relationship('User')

    @property
    def variacao_custo(self):
        """Variação percentual do custo"""
        if self.valor_custo_anterior and self.valor_custo_anterior > 0:
            return ((self.valor_custo_novo or 0) - self.valor_custo_anterior) / self.valor_custo_anterior * 100
        return None

    @property
    def variacao_receita(self):
        """Variação percentual da receita"""
        if self.valor_receita_anterior and self.valor_receita_anterior > 0:
            return ((self.valor_receita_novo or 0) - self.valor_receita_anterior) / self.valor_receita_anterior * 100
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'item_lpu_id': self.item_lpu_id,
            'item_nome': self.item_lpu.nome if self.item_lpu else 'N/A',
            # Valores monetários serializados via money_str
            'custo_anterior': money_str(self.valor_custo_anterior),
            'custo_novo': money_str(self.valor_custo_novo),
            'receita_anterior': money_str(self.valor_receita_anterior),
            'receita_novo': money_str(self.valor_receita_novo),
            'variacao_custo': round(self.variacao_custo, 2) if self.variacao_custo else None,
            'variacao_receita': round(self.variacao_receita, 2) if self.variacao_receita else None,
            'motivo': self.motivo,
            'data_alteracao': self.data_alteracao.isoformat() if self.data_alteracao else None,
            'alterado_por': self.alterado_por.username if self.alterado_por else 'Sistema'
        }


# =============================================================================
# TABELA DE PRECOS POR CONTRATO
# =============================================================================

class ContratoItem(db.Model):
    """
    Tabela de Precos Personalizada por Contrato (Cliente).
    Permite que cada cliente tenha valores diferenciados para pecas do almoxarifado.

    Se um cliente nao tiver entrada aqui, usa o valor padrao do ItemLPU.
    """
    __tablename__ = 'contrato_itens'

    id = db.Column(db.Integer, primary_key=True)

    # Relacionamentos
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True)
    item_lpu_id = db.Column(db.Integer, db.ForeignKey('itens_lpu.id'), nullable=False, index=True)

    # Valores de Preco
    valor_venda = db.Column(db.Numeric(10, 2), nullable=False)       # Preco cobrado DESTE cliente
    valor_repasse = db.Column(db.Numeric(10, 2), nullable=True)      # Opcional: repasse ao tecnico (se diferir)

    # Metadados
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraint: Um cliente nao pode ter o mesmo item duas vezes
    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'item_lpu_id', name='uq_contrato_item'),
    )

    # Relacionamentos ORM (backref definido em Cliente.itens)
    item_lpu = db.relationship('ItemLPU', backref=db.backref('precos_contrato', lazy='dynamic'))

    @property
    def margem(self):
        """Margem bruta: valor de venda - custo da peca"""
        custo = to_decimal(self.item_lpu.valor_custo) if self.item_lpu else Decimal('0')
        return to_decimal(self.valor_venda) - custo

    @property
    def margem_percent(self):
        """Margem percentual"""
        venda = to_decimal(self.valor_venda)
        if venda > 0:
            return (self.margem / venda) * 100
        return Decimal('0')

    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'cliente_nome': self.contrato.nome if self.contrato else None,
            'item_lpu_id': self.item_lpu_id,
            'item_nome': self.item_lpu.nome if self.item_lpu else None,
            # Valores monetários serializados via money_str
            'valor_venda': money_str(self.valor_venda),
            'valor_repasse': money_str(self.valor_repasse) if self.valor_repasse else None,
            'valor_custo': money_str(self.item_lpu.valor_custo) if self.item_lpu else None,
            'margem': money_str(self.margem),
            'margem_percent': round(float(self.margem_percent), 1) if self.margem_percent else 0.0,
            'ativo': self.ativo
        }

    def __repr__(self):
        return f'<ContratoItem {self.cliente.nome if self.cliente else "?"} - {self.item_lpu.nome if self.item_lpu else "?"}: R${self.valor_venda}>'


class Notification(db.Model):
    """Sistema de Notificações Internas"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(20), default='info')  # info, warning, danger, success
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.notification_type,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# GESTÃO DE ESTOQUE DECENTRALIZADO (STOCK EM TRÂNSITO)
# =============================================================================

class TecnicoStock(db.Model):
    """Estoque atual na mão do técnico"""
    __tablename__ = 'tecnico_stock'

    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    item_lpu_id = db.Column(db.Integer, db.ForeignKey('itens_lpu.id'), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraint: Um técnico não pode ter o mesmo item duas vezes
    __table_args__ = (
        db.UniqueConstraint('tecnico_id', 'item_lpu_id', name='uq_tecnico_stock_tecnico_item'),
    )

    tecnico = db.relationship('Tecnico', backref='estoque')
    item_lpu = db.relationship('ItemLPU', backref='estoque_tecnicos')

    def to_dict(self):
        return {
            'id': self.id,
            'tecnico_id': self.tecnico_id,
            'tecnico_nome': self.tecnico.nome,
            'item_lpu_id': self.item_lpu_id,
            'item_nome': self.item_lpu.nome,
            'quantidade': self.quantidade,
            'data_atualizacao': self.data_atualizacao.isoformat()
        }


class StockMovement(db.Model):
    """Histórico de Movimentações de Estoque"""
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    item_lpu_id = db.Column(db.Integer, db.ForeignKey('itens_lpu.id'), nullable=False)

    # Origem e Destino
    # Envios: Origem=NULL (Almoxarifado Central) -> Destino=Tecnico
    # Uso: Origem=Tecnico -> chamado_id preenchido
    # Devolução: Origem=Tecnico -> Destino=NULL (Almoxarifado Central)

    origem_tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=True)
    destino_tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=True)

    # Vínculo com Chamado (para movimentações tipo 'USO')
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=True, index=True)

    quantidade = db.Column(db.Integer, nullable=False)
    tipo_movimento = db.Column(db.String(20), nullable=False)  # 'ENVIO', 'USO', 'DEVOLUCAO', 'AJUSTE'
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Custo unitário no momento da movimentação (para auditoria e cálculo de média ponderada)
    custo_unitario = db.Column(db.Numeric(10, 2), nullable=True)

    observacao = db.Column(db.String(200), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    item_lpu = db.relationship('ItemLPU')
    origem_tecnico = db.relationship('Tecnico', foreign_keys=[origem_tecnico_id])
    destino_tecnico = db.relationship('Tecnico', foreign_keys=[destino_tecnico_id])
    chamado = db.relationship('Chamado', backref='movimentacoes_estoque')
    created_by = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'item_nome': self.item_lpu.nome if self.item_lpu else None,
            'item_lpu_id': self.item_lpu_id,
            'origem_tecnico': self.origem_tecnico.nome if self.origem_tecnico else 'Almoxarifado',
            'destino_tecnico': self.destino_tecnico.nome if self.destino_tecnico else 'Almoxarifado',
            'chamado_id': self.chamado_id,
            'quantidade': self.quantidade,
            'tipo_movimento': self.tipo_movimento,
            # Valor monetário serializado via money_str
            'custo_unitario': money_str(self.custo_unitario) if self.custo_unitario else None,
            'data_criacao': self.data_criacao.isoformat() if self.data_criacao else None,
            'observacao': self.observacao
        }


class SolicitacaoReposicao(db.Model):
    """Solicitações de reposição de estoque."""
    __tablename__ = 'solicitacoes_reposicao'

    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    item_lpu_id = db.Column(db.Integer, db.ForeignKey('itens_lpu.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)

    # Status: 'Pendente', 'Aprovada', 'Enviada', 'Recusada'
    status = db.Column(db.String(20), default='Pendente')

    # Justificativa/Observação
    justificativa = db.Column(db.Text, nullable=True)
    resposta_admin = db.Column(db.Text, nullable=True)

    # Rastreabilidade
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    aprovado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_resposta = db.Column(db.DateTime, nullable=True)

    # Relacionamentos
    tecnico = db.relationship('Tecnico', backref='solicitacoes_reposicao')
    item_lpu = db.relationship('ItemLPU')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    aprovado_por = db.relationship('User', foreign_keys=[aprovado_por_id])

    def to_dict(self):
        return {
            'id': self.id,
            'tecnico_nome': self.tecnico.nome if self.tecnico else 'N/A',
            'item_nome': self.item_lpu.nome if self.item_lpu else 'N/A',
            'quantidade': self.quantidade,
            'status': self.status,
            'justificativa': self.justificativa,
            'data_criacao': self.data_criacao.isoformat() if self.data_criacao else None
        }
