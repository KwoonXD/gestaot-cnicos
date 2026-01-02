from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

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
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)
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
    tags_list = db.relationship('Tag', backref='tecnico', lazy='dynamic')
    
    @property
    def id_tecnico(self):
        return f"T-{str(self.id).zfill(3)}"
    
    @property
    def localizacao(self):
        return f"{self.cidade}/{self.estado}"
    
    @property
    def identificacao_completa(self):
        return f"[{self.id_tecnico}] {self.nome} - {self.localizacao}"
    
    @property
    def total_atendimentos(self):
        return self.chamados.count()
    
    @property
    def total_atendimentos_concluidos(self):
        return self.chamados.filter_by(status_chamado='Concluído').count()
    
    @property
    def total_atendimentos_nao_pagos(self):
        # If I am a sub-technician (have a principal), my debts are handled by him.
        if self.tecnico_principal_id:
            return 0
        
        # Start with my own count
        count = self.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None).count()
        
        # Add counts from sub-technicians
        for sub in self.sub_tecnicos:
            count += sub.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None).count()
            
        return count
    
    def get_total_a_pagar(self):
        # If I am a sub-technician (have a principal), my debts are handled by him.
        if self.tecnico_principal_id:
            return 0.0
            
        # Start with my own debt
        chamados_pendentes = self.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None).all()
        total = sum(c.valor for c in chamados_pendentes)
        
        # Add debt from sub-technicians
        for sub in self.sub_tecnicos:
            sub_pendentes = sub.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None).all()
            total += sum(c.valor for c in sub_pendentes)
            
        return float(total)

    @property
    def total_a_pagar(self):
        return self.get_total_a_pagar()
    
    @property
    def total_agregado(self):
        """
        Soma o valor pendente do próprio técnico + valor pendente de todos os seus sub-técnicos.
        Usado para mostrar ao Chefe quanto ele vai receber no total.
        """
        # Valor próprio
        total = self.total_a_pagar
        
        # Valor dos filhos (recursão de 1 nível ou loop)
        for sub in self.sub_tecnicos:
            total += sub.total_a_pagar
            
        return total

    @property
    def pending_chamados_list(self):
        """Helper to get all pending chamados objects efficiently."""
        if self.tecnico_principal_id:
            return []
            
        chamados = list(self.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None))
        for sub in self.sub_tecnicos:
            chamados.extend(list(sub.chamados.filter(Chamado.status_chamado == 'Concluído', Chamado.pago == False, Chamado.pagamento_id == None)))
        return chamados

    @property
    def pending_fsas(self):
        codes = []
        for c in self.pending_chamados_list:
            if c.codigo_chamado:
                codes.append(c.codigo_chamado)
            if c.fsa_codes:
                # fsa_codes might be comma separated or single
                extras = [x.strip() for x in c.fsa_codes.replace(';', ',').split(',') if x.strip()]
                codes.extend(extras)
        # Unique and sorted
        return sorted(list(set(codes)))

    @property
    def oldest_pending_atendimento(self):
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_atendimento for c in chamados if c.data_atendimento]
        return min(dates) if dates else None

    @property
    def oldest_pending_criacao(self):
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_criacao for c in chamados if c.data_criacao]
        return min(dates) if dates else None
    
    @property
    def newest_pending_atendimento(self):
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_atendimento for c in chamados if c.data_atendimento]
        return max(dates) if dates else None

    @property
    def newest_pending_criacao(self):
        chamados = self.pending_chamados_list
        if not chamados:
            return None
        dates = [c.data_criacao for c in chamados if c.data_criacao]
        return max(dates) if dates else None

    @property
    def status_pagamento(self):
        return "Pendente" if self.total_a_pagar > 0 else "Pago"
    
    def to_dict(self):
        return {
            'id': self.id,
            'id_tecnico': self.id_tecnico,
            'nome': self.nome,
            'contato': self.contato,
            'cidade': self.cidade,
            'estado': self.estado,
            'localizacao': self.localizacao,
            'status': self.status,
            'valor_por_atendimento': float(self.valor_por_atendimento),
            'forma_pagamento': self.forma_pagamento,
            'chave_pagamento': self.chave_pagamento,
            'tecnico_principal_id': self.tecnico_principal_id,
            'tecnico_principal_nome': self.tecnico_principal.nome if self.tecnico_principal else None,
            'data_inicio': self.data_inicio.isoformat() if self.data_inicio else None,
            'data_cadastro': self.data_cadastro.isoformat() if self.data_cadastro else None,
            'total_atendimentos': self.total_atendimentos,
            'total_atendimentos_concluidos': self.total_atendimentos_concluidos,
            'total_atendimentos_nao_pagos': self.total_atendimentos_nao_pagos,
            'total_a_pagar': self.total_a_pagar,
            'status_pagamento': self.status_pagamento,
            'tags': [t.to_dict() for t in self.tags_list]
        }


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
    tipo_servico = db.Column(db.String(50), nullable=True)
    tipo_resolucao = db.Column(db.String(50), default='')
    
    status_chamado = db.Column(db.String(20), default='Finalizado')
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
    
    valor = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    pago = db.Column(db.Boolean, default=False)
    pagamento_id = db.Column(db.Integer, db.ForeignKey('pagamentos.id'), nullable=True)
    endereco = db.Column(db.Text, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    fsa_codes = db.Column(db.Text, nullable=True)
    horario_inicio = db.Column(db.Time, nullable=True)  # Legado
    horario_saida = db.Column(db.Time, nullable=True)   # Legado
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Agrupamento por Lote/Atendimento
    batch_id = db.Column(db.String(36), index=True, nullable=True)  # UUID para vincular FSAs do mesmo atendimento
    
    # Workflow de Validação
    status_validacao = db.Column(db.String(20), default='Pendente')  # 'Pendente', 'Aprovado', 'Rejeitado'
    data_validacao = db.Column(db.DateTime, nullable=True)
    validado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    validado_por = db.relationship('User', foreign_keys=[validado_por_id])
    
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
            'valor': float(self.valor) if self.valor else 0.0,
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
        # Soma custo_atribuido se existir (novo modelo), senão usa valor (legado)
        return float(sum((c.custo_atribuido if c.custo_atribuido is not None else c.valor) for c in self.chamados_incluidos))
    
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
            'valor_por_atendimento': float(self.valor_por_atendimento),
            'valor_total': self.valor_total,
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


class Lancamento(db.Model):
    __tablename__ = 'lancamentos'
    
    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    pagamento_id = db.Column(db.Integer, db.ForeignKey('pagamentos.id'), nullable=True)
    data = db.Column(db.Date, nullable=False, default=date.today)
    tipo = db.Column(db.String(20), nullable=False)  # Bonus, Desconto
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    tecnico = db.relationship('Tecnico', backref='lancamentos')
    pagamento = db.relationship('Pagamento', backref='lancamentos')
    
    def to_dict(self):
        return {
            'id': self.id,
            'tecnico_id': self.tecnico_id,
            'pagamento_id': self.pagamento_id,
            'data': self.data.isoformat() if self.data else None,
            'tipo': self.tipo,
            'valor': float(self.valor),
            'descricao': self.descricao
        }

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
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'ativo': self.ativo,
            'servicos': [s.to_dict() for s in self.tipos_servico],
            'lpu': [l.to_dict() for l in self.itens_lpu]
        }


class CatalogoServico(db.Model):
    """
    Catálogo Unificado de Serviços por Cliente.
    Une 'Tipo de Serviço' e 'Resolução' em uma única entidade com regras de negócio.
    """
    __tablename__ = 'catalogo_servicos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)  # Ex: "Zebra - 1ª Visita", "Retorno SPARE"
    valor_receita = db.Column(db.Float, default=0.0)  # Receita para a empresa (R$)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    
    # Regras de Negócio
    exige_peca = db.Column(db.Boolean, default=False)     # Se True, mostra seleção de LPU
    paga_tecnico = db.Column(db.Boolean, default=True)    # Se False (ex: Falha), técnico recebe 0
    horas_franquia = db.Column(db.Integer, default=2)     # Até quantas horas o valor base cobre
    
    # Status
    ativo = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'valor': self.valor_receita,
            'exige_peca': self.exige_peca,
            'paga_tecnico': self.paga_tecnico,
            'horas_franquia': self.horas_franquia
        }


# Alias para compatibilidade com código existente
TipoServico = CatalogoServico


class ItemLPU(db.Model):
    """Itens LPU (Peças) por Cliente - Ex: Scanner (R$ 180), Monitor (R$ 200)"""
    __tablename__ = 'itens_lpu'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor_receita = db.Column(db.Float, default=0.0)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'valor': self.valor_receita
        }


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
