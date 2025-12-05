import os
import secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, date
from models import db, Tecnico, Chamado, Pagamento, ESTADOS_BRASIL, FORMAS_PAGAMENTO

app = Flask(__name__)

session_secret = os.environ.get("SESSION_SECRET")
if not session_secret:
    session_secret = secrets.token_hex(32)
app.secret_key = session_secret

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is required")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

STATUS_TECNICO = ['Ativo', 'Inativo']
TIPOS_SERVICO = ['Americanas', 'Escolas', 'Telmex', 'Esteira']
STATUS_CHAMADO = ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']
STATUS_PAGAMENTO = ['Pendente', 'Pago', 'Cancelado']


@app.route('/')
def dashboard():
    tecnicos = Tecnico.query.all()
    chamados = Chamado.query.all()
    pagamentos = Pagamento.query.all()
    
    total_tecnicos_ativos = Tecnico.query.filter_by(status='Ativo').count()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    chamados_mes = Chamado.query.filter(
        db.extract('month', Chamado.data_atendimento) == current_month,
        db.extract('year', Chamado.data_atendimento) == current_year
    ).count()
    
    valor_total_pendente = sum(t.total_a_pagar for t in tecnicos)
    pagamentos_pendentes = Pagamento.query.filter_by(status_pagamento='Pendente').count()
    
    chamados_por_status = {}
    for status in STATUS_CHAMADO:
        chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
    
    ultimos_chamados = Chamado.query.order_by(Chamado.data_criacao.desc()).limit(5).all()
    
    return render_template('dashboard.html',
        total_tecnicos_ativos=total_tecnicos_ativos,
        chamados_mes=chamados_mes,
        valor_total_pendente=valor_total_pendente,
        pagamentos_pendentes=pagamentos_pendentes,
        chamados_por_status=chamados_por_status,
        ultimos_chamados=ultimos_chamados
    )


@app.route('/tecnicos')
def tecnicos():
    estado_filter = request.args.get('estado', '')
    cidade_filter = request.args.get('cidade', '')
    status_filter = request.args.get('status', '')
    pagamento_filter = request.args.get('pagamento', '')
    search = request.args.get('search', '')
    
    query = Tecnico.query
    
    if estado_filter:
        query = query.filter_by(estado=estado_filter)
    if cidade_filter:
        query = query.filter(Tecnico.cidade.ilike(f'%{cidade_filter}%'))
    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        query = query.filter(Tecnico.nome.ilike(f'%{search}%'))
    
    tecnicos_list = query.order_by(Tecnico.nome).all()
    
    if pagamento_filter == 'Pendente':
        tecnicos_list = [t for t in tecnicos_list if t.total_a_pagar > 0]
    elif pagamento_filter == 'Pago':
        tecnicos_list = [t for t in tecnicos_list if t.total_a_pagar == 0]
    
    estados_usados = db.session.query(Tecnico.estado).distinct().order_by(Tecnico.estado).all()
    estados_usados = [e[0] for e in estados_usados if e[0]]
    
    return render_template('tecnicos.html',
        tecnicos=tecnicos_list,
        estados=ESTADOS_BRASIL,
        estados_usados=estados_usados,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        estado_filter=estado_filter,
        cidade_filter=cidade_filter,
        status_filter=status_filter,
        pagamento_filter=pagamento_filter,
        search=search
    )


@app.route('/tecnicos/novo', methods=['GET', 'POST'])
def novo_tecnico():
    if request.method == 'POST':
        tecnico_principal_id = request.form.get('tecnico_principal_id')
        if tecnico_principal_id:
            tecnico_principal_id = int(tecnico_principal_id)
        else:
            tecnico_principal_id = None
            
        tecnico = Tecnico(
            nome=request.form['nome'],
            contato=request.form['contato'],
            cidade=request.form['cidade'],
            estado=request.form['estado'],
            status=request.form.get('status', 'Ativo'),
            valor_por_atendimento=float(request.form.get('valor_por_atendimento', 150.00)),
            forma_pagamento=request.form.get('forma_pagamento', ''),
            chave_pagamento=request.form.get('chave_pagamento', ''),
            tecnico_principal_id=tecnico_principal_id,
            data_inicio=datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        )
        db.session.add(tecnico)
        db.session.commit()
        return redirect(url_for('tecnicos'))
    
    tecnicos_principais = Tecnico.query.filter_by(status='Ativo').order_by(Tecnico.nome).all()
    
    return render_template('tecnico_form.html',
        tecnico=None,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )


@app.route('/tecnicos/<int:id>')
def tecnico_detalhes(id):
    tecnico = Tecnico.query.get_or_404(id)
    chamados = tecnico.chamados.order_by(Chamado.data_atendimento.desc()).all()
    pagamentos = tecnico.pagamentos.order_by(Pagamento.data_criacao.desc()).all()
    sub_tecnicos = tecnico.sub_tecnicos
    
    return render_template('tecnico_detalhes.html',
        tecnico=tecnico,
        chamados=chamados,
        pagamentos=pagamentos,
        sub_tecnicos=sub_tecnicos
    )


@app.route('/tecnicos/<int:id>/editar', methods=['GET', 'POST'])
def editar_tecnico(id):
    tecnico = Tecnico.query.get_or_404(id)
    
    if request.method == 'POST':
        tecnico_principal_id = request.form.get('tecnico_principal_id')
        if tecnico_principal_id:
            tecnico_principal_id = int(tecnico_principal_id)
        else:
            tecnico_principal_id = None
            
        tecnico.nome = request.form['nome']
        tecnico.contato = request.form['contato']
        tecnico.cidade = request.form['cidade']
        tecnico.estado = request.form['estado']
        tecnico.status = request.form.get('status', 'Ativo')
        tecnico.valor_por_atendimento = float(request.form.get('valor_por_atendimento', 150.00))
        tecnico.forma_pagamento = request.form.get('forma_pagamento', '')
        tecnico.chave_pagamento = request.form.get('chave_pagamento', '')
        tecnico.tecnico_principal_id = tecnico_principal_id
        tecnico.data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        db.session.commit()
        return redirect(url_for('tecnico_detalhes', id=id))
    
    tecnicos_principais = Tecnico.query.filter(
        Tecnico.status == 'Ativo',
        Tecnico.id != id
    ).order_by(Tecnico.nome).all()
    
    return render_template('tecnico_form.html',
        tecnico=tecnico,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )


@app.route('/chamados')
def chamados():
    tecnico_filter = request.args.get('tecnico', '')
    status_filter = request.args.get('status', '')
    tipo_filter = request.args.get('tipo', '')
    pago_filter = request.args.get('pago', '')
    
    query = Chamado.query.join(Tecnico)
    
    if tecnico_filter:
        query = query.filter(Chamado.tecnico_id == int(tecnico_filter))
    if status_filter:
        query = query.filter(Chamado.status_chamado == status_filter)
    if tipo_filter:
        query = query.filter(Chamado.tipo_servico == tipo_filter)
    if pago_filter == 'sim':
        query = query.filter(Chamado.pago == True)
    elif pago_filter == 'nao':
        query = query.filter(Chamado.pago == False)
    
    chamados_list = query.order_by(Chamado.data_atendimento.desc()).all()
    tecnicos_list = Tecnico.query.filter_by(status='Ativo').order_by(Tecnico.nome).all()
    
    return render_template('chamados.html',
        chamados=chamados_list,
        tecnicos=tecnicos_list,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO,
        tecnico_filter=tecnico_filter,
        status_filter=status_filter,
        tipo_filter=tipo_filter,
        pago_filter=pago_filter
    )


@app.route('/chamados/novo', methods=['GET', 'POST'])
def novo_chamado():
    if request.method == 'POST':
        chamado = Chamado(
            tecnico_id=int(request.form['tecnico_id']),
            codigo_chamado=request.form.get('codigo_chamado', ''),
            data_atendimento=datetime.strptime(request.form['data_atendimento'], '%Y-%m-%d').date(),
            tipo_servico=request.form['tipo_servico'],
            status_chamado=request.form.get('status_chamado', 'Pendente'),
            endereco=request.form.get('endereco', ''),
            observacoes=request.form.get('observacoes', '')
        )
        db.session.add(chamado)
        db.session.commit()
        return redirect(url_for('chamados'))
    
    tecnicos = Tecnico.query.filter_by(status='Ativo').order_by(Tecnico.nome).all()
    return render_template('chamado_form.html',
        chamado=None,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )


@app.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
def editar_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    
    if request.method == 'POST':
        chamado.tecnico_id = int(request.form['tecnico_id'])
        chamado.codigo_chamado = request.form.get('codigo_chamado', '')
        chamado.data_atendimento = datetime.strptime(request.form['data_atendimento'], '%Y-%m-%d').date()
        chamado.tipo_servico = request.form['tipo_servico']
        chamado.status_chamado = request.form.get('status_chamado', 'Pendente')
        chamado.endereco = request.form.get('endereco', '')
        chamado.observacoes = request.form.get('observacoes', '')
        db.session.commit()
        return redirect(url_for('chamados'))
    
    tecnicos = Tecnico.query.filter_by(status='Ativo').order_by(Tecnico.nome).all()
    return render_template('chamado_form.html',
        chamado=chamado,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )


@app.route('/chamados/<int:id>/status', methods=['POST'])
def atualizar_status_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    novo_status = request.form.get('status')
    if novo_status in STATUS_CHAMADO:
        chamado.status_chamado = novo_status
        db.session.commit()
    return redirect(url_for('chamados'))


@app.route('/pagamentos')
def pagamentos():
    tecnico_filter = request.args.get('tecnico', '')
    status_filter = request.args.get('status', '')
    
    query = Pagamento.query
    
    if tecnico_filter:
        query = query.filter(Pagamento.tecnico_id == int(tecnico_filter))
    if status_filter:
        query = query.filter(Pagamento.status_pagamento == status_filter)
    
    pagamentos_list = query.order_by(Pagamento.data_criacao.desc()).all()
    tecnicos_list = Tecnico.query.order_by(Tecnico.nome).all()
    
    tecnicos_com_pendente = [t for t in tecnicos_list if t.total_a_pagar > 0]
    
    return render_template('pagamentos.html',
        pagamentos=pagamentos_list,
        tecnicos=tecnicos_list,
        tecnicos_com_pendente=tecnicos_com_pendente,
        status_options=STATUS_PAGAMENTO,
        tecnico_filter=tecnico_filter,
        status_filter=status_filter
    )


@app.route('/pagamentos/gerar', methods=['GET', 'POST'])
def gerar_pagamento():
    if request.method == 'POST':
        tecnico_id = int(request.form['tecnico_id'])
        periodo_inicio = datetime.strptime(request.form['periodo_inicio'], '%Y-%m-%d').date()
        periodo_fim = datetime.strptime(request.form['periodo_fim'], '%Y-%m-%d').date()
        
        tecnico = Tecnico.query.get_or_404(tecnico_id)
        
        chamados_para_pagar = Chamado.query.filter(
            Chamado.tecnico_id == tecnico_id,
            Chamado.status_chamado == 'Concluído',
            Chamado.pago == False,
            Chamado.data_atendimento >= periodo_inicio,
            Chamado.data_atendimento <= periodo_fim
        ).all()
        
        if not chamados_para_pagar:
            return render_template('pagamento_gerar.html',
                tecnicos=Tecnico.query.filter_by(status='Ativo').all(),
                error="Nenhum chamado encontrado para pagamento no período selecionado."
            )
        
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pendente'
        )
        db.session.add(pagamento)
        db.session.flush()
        
        for chamado in chamados_para_pagar:
            chamado.pago = True
            chamado.pagamento_id = pagamento.id
        
        db.session.commit()
        return redirect(url_for('pagamentos'))
    
    tecnicos = [t for t in Tecnico.query.filter_by(status='Ativo').all() if t.total_a_pagar > 0]
    return render_template('pagamento_gerar.html', tecnicos=tecnicos, error=None)


@app.route('/pagamentos/<int:id>')
def pagamento_detalhes(id):
    pagamento = Pagamento.query.get_or_404(id)
    chamados = pagamento.chamados_incluidos.all()
    return render_template('pagamento_detalhes.html',
        pagamento=pagamento,
        chamados=chamados
    )


@app.route('/pagamentos/<int:id>/pagar', methods=['POST'])
def marcar_como_pago(id):
    pagamento = Pagamento.query.get_or_404(id)
    pagamento.status_pagamento = 'Pago'
    pagamento.data_pagamento = date.today()
    pagamento.observacoes = request.form.get('observacoes', '')
    db.session.commit()
    return redirect(url_for('pagamentos'))


@app.route('/api/tecnicos')
def api_tecnicos():
    tecnicos = Tecnico.query.all()
    return jsonify([t.to_dict() for t in tecnicos])


@app.route('/api/chamados')
def api_chamados():
    chamados = Chamado.query.all()
    return jsonify([c.to_dict() for c in chamados])


@app.route('/api/pagamentos')
def api_pagamentos():
    pagamentos = Pagamento.query.all()
    return jsonify([p.to_dict() for p in pagamentos])


@app.route('/api/dashboard')
def api_dashboard():
    tecnicos = Tecnico.query.all()
    
    total_tecnicos_ativos = Tecnico.query.filter_by(status='Ativo').count()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    chamados_mes = Chamado.query.filter(
        db.extract('month', Chamado.data_atendimento) == current_month,
        db.extract('year', Chamado.data_atendimento) == current_year
    ).count()
    
    valor_total_pendente = sum(t.total_a_pagar for t in tecnicos)
    pagamentos_pendentes = Pagamento.query.filter_by(status_pagamento='Pendente').count()
    
    chamados_por_status = {}
    for status in STATUS_CHAMADO:
        chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
    
    return jsonify({
        'total_tecnicos_ativos': total_tecnicos_ativos,
        'chamados_mes': chamados_mes,
        'valor_total_pendente': valor_total_pendente,
        'pagamentos_pendentes': pagamentos_pendentes,
        'chamados_por_status': chamados_por_status
    })


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
