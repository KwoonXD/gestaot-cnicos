from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
import csv
import io
# CORREÇÃO AQUI: Importamos Chamado, Pagamento e Tecnico explicitamente
from ..models import ESTADOS_BRASIL, FORMAS_PAGAMENTO, Chamado, Pagamento, Tecnico
from ..services.tecnico_service import TecnicoService
from ..services.chamado_service import ChamadoService
from ..services.financeiro_service import FinanceiroService

operacional_bp = Blueprint('operacional', __name__)

STATUS_TECNICO = ['Ativo', 'Inativo']
TIPOS_SERVICO = ['Americanas', 'Escolas', 'Telmex', 'Telmex Urgente', 'Esteira']
STATUS_CHAMADO = ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']

@operacional_bp.route('/')
@login_required
def dashboard():
    tecnico_stats = TecnicoService.get_stats()
    chamado_stats = ChamadoService.get_dashboard_stats()
    financeiro_stats = FinanceiroService.get_pendentes_stats()
    projecao_stats = FinanceiroService.calcular_projecao_mensal()
    
    return render_template('dashboard.html',
        total_tecnicos_ativos=tecnico_stats['ativos'],
        chamados_mes=chamado_stats['chamados_mes'],
        valor_total_pendente=tecnico_stats['total_pendente'],
        pagamentos_pendentes=financeiro_stats,
        chamados_por_status=chamado_stats['chamados_por_status'],
        ultimos_chamados=chamado_stats['ultimos'],
        projecao_financeira=projecao_stats
    )

@operacional_bp.route('/tecnicos')
@login_required
def tecnicos():
    filters = {
        'estado': request.args.get('estado', ''),
        'cidade': request.args.get('cidade', ''),
        'status': request.args.get('status', ''),
        'pagamento': request.args.get('pagamento', ''),
        'search': request.args.get('search', '')
    }
    
    tecnicos_list = TecnicoService.get_all(filters)
    
    # Get states for dropdown
    estados_usados = sorted(list(set([t.estado for t in tecnicos_list if t.estado])))
    
    return render_template('tecnicos.html',
        tecnicos=tecnicos_list,
        estados=ESTADOS_BRASIL,
        estados_usados=estados_usados,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        estado_filter=filters['estado'],
        cidade_filter=filters['cidade'],
        status_filter=filters['status'],
        pagamento_filter=filters['pagamento'],
        search=filters['search']
    )

# Task 3: Relatórios (Exportação CSV)
@operacional_bp.route('/tecnicos/exportar')
@login_required
def exportar_tecnicos():
    tecnicos = TecnicoService.get_all()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Header
    writer.writerow(['ID', 'Nome', 'Cidade', 'Estado', 'Status', 'Valor/Atendimento', 'Banco', 'Chave', 'Total a Pagar'])
    
    # Rows
    for t in tecnicos:
        writer.writerow([
            t.id_tecnico,
            t.nome,
            t.cidade,
            t.estado,
            t.status,
            f"R$ {t.valor_por_atendimento:.2f}".replace('.', ','),
            t.forma_pagamento or '-',
            t.chave_pagamento or '-',
            f"R$ {t.total_a_pagar:.2f}".replace('.', ',')
        ])
    
    return Response(
        output.getvalue().encode('utf-8-sig'), # utf-8-sig for Excel compatibility
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=tecnicos_export.csv"}
    )

@operacional_bp.route('/tecnicos/novo', methods=['GET', 'POST'])
@login_required
def novo_tecnico():
    if request.method == 'POST':
        try:
            TecnicoService.create(request.form)
            # Task 4: Feedback de Usuário
            flash('Técnico cadastrado com sucesso!', 'success')
            return redirect(url_for('operacional.tecnicos'))
        except Exception as e:
            flash(f'Erro ao cadastrar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'})
    
    return render_template('tecnico_form.html',
        tecnico=None,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )

@operacional_bp.route('/tecnicos/<int:id>')
@login_required
def tecnico_detalhes(id):
    tecnico = TecnicoService.get_by_id(id)
    
    # CORREÇÃO AQUI: Uso direto da classe Chamado importada
    chamados = tecnico.chamados.order_by(Chamado.data_atendimento.desc()).all()
    pagamentos = tecnico.pagamentos.all()
    sub_tecnicos = tecnico.sub_tecnicos
    
    return render_template('tecnico_detalhes.html',
        tecnico=tecnico,
        chamados=chamados,
        pagamentos=pagamentos,
        sub_tecnicos=sub_tecnicos
    )

@operacional_bp.route('/tecnicos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_tecnico(id):
    tecnico = TecnicoService.get_by_id(id)
    
    if request.method == 'POST':
        try:
            TecnicoService.update(id, request.form)
            flash('Dados do técnico atualizados com sucesso!', 'success')
            return redirect(url_for('operacional.tecnico_detalhes', id=id))
        except Exception as e:
            flash(f'Erro ao atualizar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'})
    tecnicos_principais = [t for t in tecnicos_principais if t.id != id]
    
    return render_template('tecnico_form.html',
        tecnico=tecnico,
        estados=ESTADOS_BRASIL,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        tecnicos_principais=tecnicos_principais
    )

@operacional_bp.route('/chamados')
@login_required
def chamados():
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', ''),
        'tipo': request.args.get('tipo', ''),
        'pago': request.args.get('pago', ''),
        'search': request.args.get('search', '')
    }
    
    chamados_list = ChamadoService.get_all(filters)
    tecnicos_list = TecnicoService.get_all({'status': 'Ativo'})
    
    chamados_list = ChamadoService.get_all(filters)
    tecnicos_list = TecnicoService.get_all({'status': 'Ativo'})
    
    # Task 2: Saved Views
    from ..models import SavedView
    saved_views = SavedView.query.filter_by(user_id=current_user.id, page_route='chamados').all()
    
    return render_template('chamados.html',
        chamados=chamados_list,
        tecnicos=tecnicos_list,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO,
        tecnico_filter=filters['tecnico_id'],
        status_filter=filters['status'],
        tipo_filter=filters['tipo'],
        pago_filter=filters['pago'],
        search_filter=filters['search'],
        saved_views=saved_views
    )

@operacional_bp.route('/api/views/save', methods=['POST'])
@login_required
def salvar_view():
    try:
        data = request.get_json()
        from ..models import SavedView, db
        
        view = SavedView(
            user_id=current_user.id,
            page_route=data.get('page_route'),
            name=data.get('name'),
            query_string=data.get('query_string')
        )
        db.session.add(view)
        db.session.commit()
        return {'status': 'success', 'id': view.id}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 400

@operacional_bp.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    if request.method == 'POST':
        try:
            ChamadoService.create(request.form)
            flash('Chamado registrado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            flash(f'Erro: {str(e)}', 'warning')
            
            # Preserve form data for template
            from datetime import datetime
            import types
            
            form_data = request.form
            chamado_mock = types.SimpleNamespace()
            
            # Safe parsing
            def parse_date(d):
                try: return datetime.strptime(d, '%Y-%m-%d')
                except: return None
            def parse_time(t):
                try: return datetime.strptime(t, '%H:%M')
                except: return None
                
            chamado_mock.tecnico_id = form_data.get('tecnico_id')
            chamado_mock.codigo_chamado = form_data.get('codigo_chamado')
            chamado_mock.data_atendimento = parse_date(form_data.get('data_atendimento'))
            chamado_mock.tipo_servico = form_data.get('tipo_servico')
            chamado_mock.status_chamado = form_data.get('status_chamado')
            chamado_mock.horario_inicio = parse_time(form_data.get('horario_inicio'))
            chamado_mock.horario_saida = parse_time(form_data.get('horario_saida'))
            chamado_mock.fsa_codes = form_data.get('fsa_codes')
            try:
                chamado_mock.valor = float(form_data.get('valor', 0))
            except:
                chamado_mock.valor = 0.0
            chamado_mock.endereco = form_data.get('endereco')
            chamado_mock.observacoes = form_data.get('observacoes')
            
            if chamado_mock.tecnico_id:
                try:
                    chamado_mock.tecnico = TecnicoService.get_by_id(chamado_mock.tecnico_id)
                except:
                    chamado_mock.tecnico = None
            else:
                 chamado_mock.tecnico = None
            
            tecnicos = TecnicoService.get_all({'status': 'Ativo'})
            return render_template('chamado_form.html',
                chamado=chamado_mock,
                tecnicos=tecnicos,
                tipos_servico=TIPOS_SERVICO,
                status_options=STATUS_CHAMADO
            )
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=None,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    chamado = ChamadoService.get_by_id(id)
    
    if request.method == 'POST':
        try:
            ChamadoService.update(id, request.form)
            flash('Chamado atualizado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            flash(f'Erro ao atualizar chamado: {str(e)}', 'danger')
    
    tecnicos = TecnicoService.get_all({'status': 'Ativo'})
    return render_template('chamado_form.html',
        chamado=chamado,
        tecnicos=tecnicos,
        tipos_servico=TIPOS_SERVICO,
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status_chamado(id):
    try:
        ChamadoService.update_status(id, request.form.get('status'))
        flash('Status do chamado atualizado.', 'info')
    except Exception as e:

            flash(f'Erro ao atualizar status: {str(e)}', 'danger')
    return redirect(url_for('operacional.chamados'))

@operacional_bp.route('/tecnicos/<int:id>/resumo')
@login_required
def tecnico_resumo(id):
    tecnico = TecnicoService.get_by_id(id)
    return render_template('tecnico_resumo.html', tecnico=tecnico)

@operacional_bp.route('/tecnicos/<int:id>/tags/criar', methods=['POST'])
@login_required
def criar_tag(id):
    try:
        from ..models import Tag, db
        nome = request.form.get('nome')
        cor = request.form.get('cor', '#3B82F6')
        
        if nome:
            tag = Tag(nome=nome, cor=cor, tecnico_id=id)
            db.session.add(tag)
            db.session.commit()
            flash('Tag adicionada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar tag: {str(e)}', 'danger')
        
    return redirect(url_for('operacional.tecnico_detalhes', id=id))

@operacional_bp.route('/tags/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_tag(id):
    try:
        from ..models import Tag, db
        tag = Tag.query.get_or_404(id)
        tecnico_id = tag.tecnico_id
        db.session.delete(tag)
        db.session.commit()
        flash('Tag removida com sucesso!', 'success')
        return redirect(url_for('operacional.tecnico_detalhes', id=tecnico_id))
    except Exception as e:
        flash(f'Erro ao remover tag: {str(e)}', 'danger')
        # In case of error, we might not have tecnico_id if tag fetch failed, 
        # but here we assume tag exists or 404.
        return redirect(url_for('operacional.tecnicos'))

