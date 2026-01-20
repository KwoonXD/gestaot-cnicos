from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify
from flask_login import login_required, current_user
import csv
import io
from sqlalchemy import func
# CORREÇÃO AQUI: Importamos Chamado, Pagamento e Tecnico explicitamente
from ..models import ESTADOS_BRASIL, FORMAS_PAGAMENTO, Chamado, Pagamento, Tecnico, Tag, Cliente, db, TecnicoStock, ItemLPU
from ..services.tecnico_service import TecnicoService
from ..services.chamado_service import ChamadoService
from ..services.financeiro_service import FinanceiroService
from ..services.tag_service import TagService
from ..services.saved_view_service import SavedViewService
from ..services.import_service import ImportService
from ..services.report_service import ReportService
from ..services.stock_service import StockService
from ..decorators import admin_required

operacional_bp = Blueprint('operacional', __name__)

@operacional_bp.route('/tecnicos/importar', methods=['GET', 'POST'])
@login_required
def importar_tecnicos():
    if request.method == 'POST':
        if 'arquivo_excel' not in request.files:
            flash('Nenhum arquivo enviado.', 'danger')
            return redirect(request.url)
            
        file = request.files['arquivo_excel']
        if file.filename == '':
            flash('Nenhum arquivo selecionado.', 'danger')
            return redirect(request.url)

        if file:
            try:
                result = ImportService.importar_tecnicos(file)
                if result['success']:
                    db.session.commit()
                    flash(result['message'], 'success')
                    return redirect(url_for('operacional.tecnicos'))
                else:
                    db.session.rollback()
                    flash(result['message'], 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f'Erro na importação: {str(e)}', 'danger')
                
    return render_template('importar_tecnicos.html')

STATUS_TECNICO = ['Ativo', 'Inativo']
# TIPOS_SERVICO removed: Fetch dynamically from CatalogoServico
STATUS_CHAMADO = ['Pendente', 'Em Andamento', 'Concluído', 'SPARE', 'Cancelado']

# Helper to get Types
def get_tipos_servico():
    from ..models import CatalogoServico
    # Get distinct names or all active
    # Using distinct names used in system + catalog
    return [s.nome for s in CatalogoServico.query.with_entities(CatalogoServico.nome).distinct().order_by(CatalogoServico.nome).all()]


@operacional_bp.route('/')
@login_required
def dashboard():
    kpis = ReportService.get_dashboard_kpis()
    ultimos_chamados = ChamadoService.get_dashboard_stats().get('ultimos', [])
    alertas_estoque = StockService.get_alertas_dashboard(limite_minimo=10)

    return render_template('dashboard.html',
        kpis=kpis,
        ultimos_chamados=ultimos_chamados,
        alertas_estoque=alertas_estoque
    )

@operacional_bp.route('/tecnicos')
@login_required
def tecnicos():
    page = request.args.get('page', 1, type=int)
    filters = {
        'estado': request.args.get('estado', ''),
        'cidade': request.args.get('cidade', ''),
        'status': request.args.get('status', ''),
        'pagamento': request.args.get('pagamento', ''),
        'search': request.args.get('search', ''),
        'tag': request.args.get('tag', '')
    }
    
    # REFATORADO: Usar get_tecnicos_com_metricas() em vez de get_all()
    # Isso retorna TecnicoMetricas DTOs com total_a_pagar_agregado já calculado
    result = TecnicoService.get_tecnicos_com_metricas(
        filters=filters, 
        page=page, 
        per_page=20
    )
    
    # result['items'] = lista de TecnicoMetricas
    # result['pagination'] = dict com info de paginação ou None
    metricas_list = result['items']
    pagination_info = result.get('pagination')
    
    # Para compatibilidade com template, passamos os objetos como lista
    # O template pode acessar m.tecnico para dados do Model ou m.total_a_pagar_agregado
    
    # Get states for dropdown (usando os técnicos retornados)
    all_states = [m.tecnico.estado for m in metricas_list if m.tecnico.estado] 
    estados_usados = sorted(list(set(all_states)))
    
    saved_views = SavedViewService.get_for_user(current_user.id, 'tecnicos')
    available_tags = TagService.get_all_unique()
    tecnicos_por_estado = TecnicoService.get_distribuicao_geografica()

    # Criar objeto de paginação compatível com template
    class PaginationShim:
        """Shim para compatibilidade com template existente."""
        def __init__(self, items, info):
            self.items = items
            self.page = info.get('page', 1) if info else 1
            self.pages = info.get('pages', 1) if info else 1
            self.total = info.get('total', len(items)) if info else len(items)
            self.has_next = info.get('has_next', False) if info else False
            self.has_prev = info.get('has_prev', False) if info else False
            self.next_num = info.get('next_num') if info else None
            self.prev_num = info.get('prev_num') if info else None
        
        def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
            last = 0
            for num in range(1, self.pages + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = PaginationShim(metricas_list, pagination_info)

    return render_template('tecnicos.html',
        tecnicos=metricas_list,  # Lista de TecnicoMetricas
        pagination=pagination,
        estados=ESTADOS_BRASIL,
        estados_usados=estados_usados,
        formas_pagamento=FORMAS_PAGAMENTO,
        status_options=STATUS_TECNICO,
        estado_filter=filters['estado'],
        cidade_filter=filters['cidade'],
        status_filter=filters['status'],
        pagamento_filter=filters['pagamento'],
        search_filter=filters['search'],
        tag_filter=filters['tag'],
        saved_views=saved_views,
        available_tags=available_tags,
        tecnicos_por_estado=tecnicos_por_estado
    )

# Task 3: Relatórios (Exportação CSV)
@operacional_bp.route('/tecnicos/exportar')
@login_required
def exportar_tecnicos():
    # CORRIGIDO: Usar get_tecnicos_com_metricas() para ter total_a_pagar correto
    from ..services.tecnico_service import TecnicoMetricas
    result = TecnicoService.get_tecnicos_com_metricas(page=None)
    metricas_list = result['items']  # Lista de TecnicoMetricas

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header
    writer.writerow(['ID', 'Nome', 'Cidade', 'Estado', 'Status', 'Valor/Atendimento', 'Banco', 'Chave', 'Total a Pagar', 'Tags'])

    # Rows - usar TecnicoMetricas para acesso otimizado
    for m in metricas_list:
        t = m.tecnico
        tags_str = ", ".join([tag.nome for tag in t.tags])
        writer.writerow([
            t.id_tecnico,
            t.nome,
            t.cidade,
            t.estado,
            t.status,
            f"R$ {float(t.valor_por_atendimento or 0):.2f}".replace('.', ','),
            t.forma_pagamento or '-',
            t.chave_pagamento or '-',
            f"R$ {m.total_a_pagar_agregado:.2f}".replace('.', ','),
            tags_str
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
            TecnicoService.create(request.form.to_dict())
            db.session.commit()  # P0.2: Boundary commit
            # Task 4: Feedback de Usuário
            flash('Técnico cadastrado com sucesso!', 'success')
            return redirect(url_for('operacional.tecnicos'))
        except Exception as e:
            db.session.rollback()  # P0.2: Boundary rollback
            flash(f'Erro ao cadastrar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'}, page=None)

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
    from sqlalchemy import case 
    tecnico = TecnicoService.get_by_id(id)
    
    # 1. Stats Calculation
    # REFATORADO: Removido fallback para Chamado.valor (campo DEPRECATED)
    val_term = func.coalesce(Chamado.custo_atribuido, 0)
    
    stats = db.session.query(
        func.count(Chamado.id).label('total'),
        func.sum(case(
            (
                (Chamado.status_chamado.in_(['Concluído', 'SPARE'])) & 
                (Chamado.status_validacao == 'Aprovado') &  # P0: Gate unificado
                (Chamado.pago == False) & 
                (Chamado.pagamento_id == None) &
                (val_term > 0), # Apenas chamados com valor > 0 contam como 'Pendente Financeiro'
                1
            ), 
            else_=0
        )).label('pendentes_qtd'),
        func.sum(case(
            (
                (Chamado.status_chamado.in_(['Concluído', 'SPARE'])) & 
                (Chamado.status_validacao == 'Aprovado') &  # P0: Gate unificado
                (Chamado.pago == False) & 
                (Chamado.pagamento_id == None) &
                (val_term > 0),
                val_term
            ), 
            else_=0
        )).label('valor_pendente')
    ).filter_by(tecnico_id=id).first()
    
    # Ensure stats has default values (handle None from empty aggregations)
    stats = {
        'total': stats.total if stats and stats.total else 0,
        'pendentes_qtd': stats.pendentes_qtd if stats and stats.pendentes_qtd else 0,
        'valor_pendente': stats.valor_pendente if stats and stats.valor_pendente else 0.0
    }

    # 2. Pagination for History
    page = request.args.get('page', 1, type=int)
    pagination = tecnico.chamados.order_by(Chamado.data_atendimento.desc()).paginate(page=page, per_page=20)
    
    # 3. Payments
    pagamentos = tecnico.pagamentos.order_by(Pagamento.data_criacao.desc()).all()
    pagamentos_recentes = pagamentos[:5]
    sub_tecnicos = tecnico.sub_tecnicos
    
    return render_template('tecnico_detalhes.html',
        tecnico=tecnico,
        stats=stats,
        pagination=pagination,
        chamados=pagination.items,
        pagamentos=pagamentos,
        pagamentos_recentes=pagamentos_recentes,
        sub_tecnicos=sub_tecnicos
    )

@operacional_bp.route('/tecnicos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_tecnico(id):
    tecnico = TecnicoService.get_by_id(id)
    
    if request.method == 'POST':
        try:
            TecnicoService.update(id, request.form.to_dict())
            db.session.commit()  # P0.2: Boundary commit
            flash('Dados do técnico atualizados com sucesso!', 'success')
            return redirect(url_for('operacional.tecnico_detalhes', id=id))
        except Exception as e:
            db.session.rollback()  # P0.2: Boundary rollback
            flash(f'Erro ao atualizar técnico: {str(e)}', 'danger')
    
    tecnicos_principais = TecnicoService.get_all({'status': 'Ativo'}, page=None)
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
    page = request.args.get('page', 1, type=int)
    filters = {
        'tecnico_id': request.args.get('tecnico', ''),
        'status': request.args.get('status', ''),
        'status_validacao': request.args.get('status_validacao', ''), # Default handled below
        'tipo': request.args.get('tipo', ''),
        'pago': request.args.get('pago', ''),
        'search': request.args.get('search', '')
    }
    
    # Default to "Inbox mode" if not searching specifically
    # User Request: "na aba chamados deveria ser apenas ... pendente de ser validado"
    # Show Pendente/Rejeitado by default. Hide Aprovado/Excluído.
    view_mode = request.args.get('view', 'inbox')
    
    if not filters['status_validacao']:
        if view_mode == 'all':
            filters['status_validacao'] = [] # No filter
        else:
             filters['status_validacao'] = ['Pendente', 'Rejeitado']
    
    pagination = ChamadoService.get_all(filters, page=page, per_page=50) # 50 por página
    chamados_list = pagination.items
    
    # Para o filtro de técnicos no select (apenas ativos para não pesar)
    tecnicos_list = TecnicoService.get_all({'status': 'Ativo'}, page=1, per_page=1000).items
    
    # Task 2: Saved Views
    saved_views = SavedViewService.get_for_user(current_user.id, 'chamados')
    
    return render_template('chamados.html',
        chamados=chamados_list,
        pagination=pagination, # Passamos o objeto de paginação
        tecnicos=tecnicos_list,
        tipos_servico=get_tipos_servico(),
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
        SavedViewService.save_view(current_user.id, data.get('page_route'), data.get('name'), data.get('query_string'))
        db.session.commit()  # P0.2: Boundary commit
        return {'status': 'success'}
    except Exception as e:
        db.session.rollback()  # P0.2: Boundary rollback
        return {'status': 'error', 'message': str(e)}, 400

@operacional_bp.route('/api/views/<int:id>/delete', methods=['POST'])
@login_required
def deletar_view(id):
    try:
        SavedViewService.delete_view(id)
        db.session.commit()  # P0.2: Boundary commit
        return {'status': 'success'}
    except Exception as e:
        db.session.rollback()  # P0.2: Boundary rollback
        return {'status': 'error', 'message': str(e)}, 400

@operacional_bp.route('/chamados/criar/multiplo', methods=['POST'])
@login_required
def criar_chamado_multiplo_api():
    """API endpoint for Master-Detail form (batch creation)"""
    try:
        data = request.get_json()
        logistica = data.get('logistica')
        fsas = data.get('fsas')
        
        if not logistica or not fsas:
            return jsonify({'error': 'Dados incompletos'}), 400
            
        ChamadoService.create_multiplo(logistica, fsas)
        db.session.commit()
        
        return jsonify({'message': 'Atendimento registrado com sucesso!'}), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@operacional_bp.route('/chamados/criar', methods=['GET'])
@login_required
def criar_chamado():
    """Renders the new Master-Detail form for creating chamados"""
    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
    return render_template('chamado_form.html', tecnicos=tecnicos)

@operacional_bp.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    if request.method == 'POST':
        try:
            ChamadoService.create(request.form)
            db.session.commit()
            flash('Chamado registrado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {str(e)}', 'warning')

            # Repopulate form data for template
            tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
            return render_template('chamado_form.html',
                chamado=request.form,  # Pass dictionary/ImmutableMultiDict directly
                tecnicos=tecnicos,
                tipos_servico=get_tipos_servico(),
                status_options=STATUS_CHAMADO
            )

    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
    return render_template('chamado_form.html',
        chamado=None,
        tecnicos=tecnicos,
        tipos_servico=get_tipos_servico(),
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    chamado = ChamadoService.get_by_id(id)

    if request.method == 'POST':
        try:
            ChamadoService.update(id, request.form)
            db.session.commit()
            flash('Chamado atualizado com sucesso!', 'success')
            return redirect(url_for('operacional.chamados'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar chamado: {str(e)}', 'danger')

    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
    return render_template('chamado_form.html',
        chamado=chamado,
        tecnicos=tecnicos,
        tipos_servico=get_tipos_servico(),
        status_options=STATUS_CHAMADO
    )

@operacional_bp.route('/chamados/<int:id>/status', methods=['POST'])
@login_required
@admin_required  # P0: Restringir mudança de status
def atualizar_status_chamado(id):
    try:
        ChamadoService.update_status(id, request.form.get('status'))
        db.session.commit()
        flash('Status do chamado atualizado.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar status: {str(e)}', 'danger')
    return redirect(url_for('operacional.chamados'))

@operacional_bp.route('/api/chamados/<int:id>', methods=['GET'])
@login_required
def get_chamado_api(id):
    chamado = ChamadoService.get_by_id(id)
    if not chamado:
        return jsonify({'error': 'Chamado não encontrado'}), 404
        
    return jsonify({
        'id': chamado.id,
        'codigo_chamado': chamado.codigo_chamado,
        'tecnico_id': chamado.tecnico_id,
        'status_chamado': chamado.status_chamado,
        'data_atendimento': chamado.data_atendimento.isoformat() if chamado.data_atendimento else None,
        'fsa_codes': chamado.fsa_codes,
        'observacoes': chamado.observacoes
    })

@operacional_bp.route('/api/chamados/<int:id>/editar-rapido', methods=['POST'])
@login_required
@admin_required  # P0: Restringir edição rápida que bypassa regras
def editar_chamado_rapido(id):
    """
    Edição rápida de chamado.
    
    REFATORADO (2026-01): Adicionado @admin_required para evitar
    bypass de regras de negócio por usuários não autorizados.
    """
    from ..services.audit_service import AuditService
    
    try:
        data = request.get_json()
        chamado = ChamadoService.get_by_id(id)
        if not chamado:
            return jsonify({'error': 'Chamado não encontrado'}), 404
        
        changes = {}
        
        # Update allowed fields with tracking
        if 'status' in data:
            changes['status_chamado'] = {'from': chamado.status_chamado, 'to': data['status']}
            chamado.status_chamado = data['status']
        if 'tecnico_id' in data:
            changes['tecnico_id'] = {'from': chamado.tecnico_id, 'to': int(data['tecnico_id'])}
            chamado.tecnico_id = int(data['tecnico_id'])
        if 'data_atendimento' in data and data['data_atendimento']:
            from datetime import datetime
            new_date = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
            changes['data_atendimento'] = {'from': str(chamado.data_atendimento), 'to': str(new_date)}
            chamado.data_atendimento = new_date
        if 'fsa_codes' in data:
            changes['fsa_codes'] = {'from': chamado.fsa_codes, 'to': data['fsa_codes']}
            chamado.fsa_codes = data['fsa_codes']
        if 'observacoes' in data:
            changes['observacoes'] = {'from': chamado.observacoes[:50] if chamado.observacoes else None, 'to': data['observacoes'][:50] if data['observacoes'] else None}
            chamado.observacoes = data['observacoes']
        
        db.session.commit()
        
        # Audit log
        if changes:
            AuditService.log_change(
                model_name='Chamado',
                object_id=id,
                action='QUICK_EDIT',
                changes=str(changes)
            )
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@operacional_bp.route('/tecnicos/<int:id>/resumo')
@login_required
def tecnico_resumo(id):
    tecnico = TecnicoService.get_by_id(id)
    return render_template('tecnico_resumo.html', tecnico=tecnico)

@operacional_bp.route('/tecnicos/<int:id>/tags/criar', methods=['POST'])
@login_required
def criar_tag(id):
    try:
        nome = request.form.get('nome')
        cor = request.form.get('cor', '#3B82F6')
        
        if nome:
            TagService.create_tag({'nome': nome, 'cor': cor, 'tecnico_id': id})
            db.session.commit()  # P0.2: Boundary commit
            flash('Tag adicionada com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()  # P0.2: Boundary rollback
        flash(f'Erro ao adicionar tag: {str(e)}', 'danger')
        
    return redirect(url_for('operacional.tecnico_detalhes', id=id))

@operacional_bp.route('/tags/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_tag(id):
    try:
        tecnico_id = TagService.delete_tag(id)
        db.session.commit()  # P0.2: Boundary commit
        flash('Tag removida com sucesso!', 'success')
        return redirect(url_for('operacional.tecnico_detalhes', id=tecnico_id))
    except Exception as e:
        db.session.rollback()  # P0.2: Boundary rollback
        flash(f'Erro ao remover tag: {str(e)}', 'danger')
        return redirect(url_for('operacional.tecnicos'))

@operacional_bp.route('/chamados/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def deletar_chamado(id):
    try:
        from ..services.chamado_service import ChamadoService
        ChamadoService.delete(id, current_user.id)
        db.session.commit()
        flash('Chamado excluído com sucesso!', 'success')
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir chamado: {str(e)}', 'danger')
        
    return redirect(url_for('operacional.chamados'))

@operacional_bp.route('/tecnicos/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def deletar_tecnico(id):
    try:
        from ..services.tecnico_service import TecnicoService
        TecnicoService.delete(id, current_user.id)
        db.session.commit()  # P0.2: Boundary commit
        flash('Técnico excluído com sucesso!', 'success')
        return redirect(url_for('operacional.tecnicos'))
    except ValueError as e:
        db.session.rollback()  # P0.2: Boundary rollback
        flash(str(e), 'danger')
        return redirect(url_for('operacional.tecnico_detalhes', id=id))
    except Exception as e:
        db.session.rollback()  # P0.2: Boundary rollback
        flash(f'Erro ao excluir técnico: {str(e)}', 'danger')
        return redirect(url_for('operacional.tecnicos'))





# =============================================================================
# ATENDIMENTOS (INBOX DE VALIDAÇÃO POR LOTE)
# =============================================================================

@operacional_bp.route('/atendimentos')
@login_required
@admin_required  # P0: Apenas admin pode ver inbox de validação
def atendimentos():
    """Inbox de lotes pendentes de validação"""
    batches = ChamadoService.get_pending_batches()
    return render_template('atendimentos.html', batches=batches)


@operacional_bp.route('/atendimentos/validar', methods=['POST'])
@login_required
@admin_required  # P0: Apenas admin pode aprovar/rejeitar lotes
def validar_atendimento():
    """Aprova ou rejeita um lote inteiro de chamados"""
    is_ajax = request.form.get('ajax') == 'true'
    
    try:
        batch_id = request.form.get('batch_id')
        acao = request.form.get('acao')
        motivo = request.form.get('motivo', '').strip()
        
        if not batch_id:
            msg = 'Lote não identificado.'
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('operacional.atendimentos'))
        
        if acao == 'aprovar':
            count = ChamadoService.aprovar_batch(batch_id, current_user.id)
            db.session.commit()
            msg = f'✅ Lote aprovado! {count} chamado(s) liberados para o Financeiro.'
            if is_ajax: return jsonify({'success': True, 'message': msg})
            flash(msg, 'success')
            
        elif acao == 'rejeitar':
            if not motivo or len(motivo) < 10:
                msg = 'O motivo da rejeição deve ter no mínimo 10 caracteres.'
                if is_ajax: return jsonify({'success': False, 'message': msg}), 400
                flash(msg, 'danger')
                return redirect(url_for('operacional.atendimentos'))
                
            count = ChamadoService.rejeitar_batch(batch_id, current_user.id, motivo)
            db.session.commit()
            msg = f'❌ Lote rejeitado. {count} chamado(s) excluídos e criadores notificados.'
            if is_ajax: return jsonify({'success': True, 'message': msg})
            flash(msg, 'warning')
            
        else:
            msg = 'Ação inválida.'
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            response['message'] = 'Ação inválida.'
            
    except Exception as e:
        db.session.rollback()
        response['message'] = f'Erro ao processar validação: {str(e)}'
    
    if is_ajax:
        return jsonify(response)
    
    flash(response['message'], 'success' if response['success'] else 'danger')
    return redirect(url_for('operacional.atendimentos'))

@operacional_bp.route('/chamados/atualizar_inline', methods=['POST'])
@login_required
@admin_required
def atualizar_chamado_inline():
    """Allows Admin to edit specific fields of a Chamado during Validation"""
    from ..models import Chamado, db
    from ..services.chamado_service import ChamadoService
    
    try:
        data = request.get_json()
        chamado_id = data.get('id')
        
        if not chamado_id:
            return jsonify({'success': False, 'message': 'ID não fornecido'}), 400
            
        chamado = Chamado.query.get(chamado_id)
        if not chamado:
             return jsonify({'success': False, 'message': 'Chamado não encontrado'}), 404
             
        # Update fields using Service to ensure consistency/logs
        # Service update usually expects a form-like dict or specific args.
        # We can pass a dict with only changed fields.
        
        # Log changes for audit (Implicit in Service if implemented, else explicit)
        # ChamadoService.update handles basic logging but expects mapped fields.
        
        update_data = {
            'horas_trabalhadas': data.get('horas_trabalhadas'),
            'custo_atribuido': data.get('custo_atribuido'),
            'observacoes': data.get('observacoes')
        }
        
        ChamadoService.update(chamado_id, update_data, user_id=current_user.id)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Atualizado com sucesso'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# =============================================================================
# NOTIFICAÇÕES
# =============================================================================

@operacional_bp.route('/notificacoes')
@login_required
def minhas_notificacoes():
    """Lista notificações do usuário"""
    from ..models import Notification
    
    notificacoes = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notificacoes.html', notificacoes=notificacoes)


@operacional_bp.route('/notificacoes/marcar-lidas', methods=['POST'])
@login_required
def marcar_notificacoes_lidas():
    """Marca todas as notificações como lidas"""
    from ..models import Notification, db
    
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    flash('Notificações marcadas como lidas.', 'success')
    return redirect(url_for('operacional.minhas_notificacoes'))


@operacional_bp.route('/notificacoes/<int:id>/ler', methods=['POST'])
@login_required
def ler_notificacao(id):
    """Marca uma notificação específica como lida"""
    from ..models import Notification, db
    
    notif = Notification.query.get_or_404(id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    
    return jsonify({'success': True})

# =============================================================================
# RELATÓRIOS
# =============================================================================

@operacional_bp.route('/relatorios/fechamento')
@login_required
def relatorio_fechamento():
    """Tela de Relatório de Fechamento por Contrato"""
    from datetime import datetime, date
    
    # Filtros
    cliente_id = request.args.get('cliente')
    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    estado = request.args.get('estado')
    
    # Defaults
    today = date.today()
    if not data_inicio_str:
        data_inicio = date(today.year, today.month, 1)
        data_inicio_str = data_inicio.strftime('%Y-%m-%d')
    else:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        
    if not data_fim_str:
        data_fim = today
        data_fim_str = data_fim.strftime('%Y-%m-%d')
    else:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        
    # Dados para dropdowns
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    report_data = None
    if cliente_id:
        report_data = ChamadoService.get_relatorio_faturamento(
            cliente_id, data_inicio, data_fim, estado
        )
        
    return render_template('relatorios/fechamento.html',
        clientes=clientes,
        estados=ESTADOS_BRASIL,
        report=report_data,
        filters={
            'cliente': int(cliente_id) if cliente_id else '',
            'inicio': data_inicio_str,
            'fim': data_fim_str,
            'estado': estado or ''
        }
    )

@operacional_bp.route('/relatorios/fechamento/exportar')
@login_required
def exportar_fechamento():
    """Exporta CSV do fechamento"""
    from datetime import datetime
    
    cliente_id = request.args.get('cliente')
    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    estado = request.args.get('estado')
    
    if not cliente_id or not data_inicio_str or not data_fim_str:
        flash('Filtros inválidos para exportação', 'danger')
        return redirect(url_for('operacional.relatorio_fechamento'))
        
    data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    
    report_data = ChamadoService.get_relatorio_faturamento(
        cliente_id, data_inicio, data_fim, estado
    )
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Header
    writer.writerow(['Data', 'Código FSA', 'Cidade', 'Estado', 'Serviço', 'Valor Ticket'])
    
    # Rows
    for item in report_data['itens']:
        writer.writerow([
            item['data'],
            item['codigo'],
            item['cidade'],
            item['estado'],
            item['servico'],
            str(item['valor']).replace('.', ',')
        ])
        
    # Footer
    writer.writerow([])
    writer.writerow(['', '', '', '', 'TOTAL GERAL', str(report_data['total_geral']).replace('.', ',')])
    
    filename = f"fechamento_contrato_{data_inicio_str}_{data_fim_str}.csv"
    
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


