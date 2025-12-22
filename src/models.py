from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
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
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Tecnico(db.Model):
    __tablename__ = 'tecnicos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    contato = db.Column(db.String(20), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)
    status = db.Column(db.String(20), default='Ativo')
    valor_por_atendimento = db.Column(db.Numeric(10, 2), default=150.00)
    forma_pagamento = db.Column(db.String(50), nullable=True)
    chave_pagamento = db.Column(db.String(200), nullable=True)
    tecnico_principal_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=True)
    data_inicio = db.Column(db.Date, nullable=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    
    tecnico_principal = db.relationship('Tecnico', remote_side=[id], backref='sub_tecnicos', foreign_keys=[tecnico_principal_id])
    chamados = db.relationship('Chamado', backref='tecnico', lazy='dynamic', foreign_keys='Chamado.tecnico_id')
    pagamentos = db.relationship('Pagamento', backref='tecnico', lazy='dynamic')
    
    @property
    def id_tecnico(self):
        return f"T-{str(self.id).zfill(3)}"
    
    @property
    def localizacao(self):
        return f"{self.cidade}/{self.estado}"
    
    @property
    def total_atendimentos(self):
        return self.chamados.count()
    
    @property
    def total_atendimentos_concluidos(self):
        return self.chamados.filter_by(status_chamado='Concluído').count()
    
    @property
    def total_atendimentos_nao_pagos(self):
        return self.chamados.filter_by(status_chamado='Concluído', pago=False).count()
    
    def get_total_a_pagar(self):
        # Calculation moved to method to allow flexibility if logic changes in service
        # But keeping property for template compatibility if needed, calling service logic pref.
        # For model, we stick to data
        chamados_pendentes = self.chamados.filter_by(status_chamado='Concluído', pago=False).all()
        return float(sum(c.valor for c in chamados_pendentes))

    @property
    def total_a_pagar(self):
        return self.get_total_a_pagar()
    
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
            'status_pagamento': self.status_pagamento
        }


class Chamado(db.Model):
    __tablename__ = 'chamados'
    
    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    codigo_chamado = db.Column(db.String(100), nullable=True)
    data_atendimento = db.Column(db.Date, nullable=False)
    tipo_servico = db.Column(db.String(50), nullable=False)
    status_chamado = db.Column(db.String(20), default='Pendente')
    valor = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    pago = db.Column(db.Boolean, default=False)
    pagamento_id = db.Column(db.Integer, db.ForeignKey('pagamentos.id'), nullable=True)
    endereco = db.Column(db.Text, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    fsa_codes = db.Column(db.Text, nullable=True)
    horario_inicio = db.Column(db.Time, nullable=True)
    horario_saida = db.Column(db.Time, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
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
        return float(sum(c.valor for c in self.chamados_incluidos))
    
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
