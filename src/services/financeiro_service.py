from datetime import datetime
import calendar
import logging
from sqlalchemy import func
# Importamos o executor global que criamos acima
from src import executor, db
from src.models import Chamado, Pagamento, Tecnico
from src.services.pricing_service import PricingService

# Logger dedicado para tarefas de background (funciona fora do app_context)
logger = logging.getLogger(__name__)


# Funcao auxiliar de calculo - DELEGADA ao PricingService
def processar_custos_chamados(chamados, tecnico):
    """
    Calcula custos de chamados aplicando regras de LOTE.

    REFATORADO (2025): Delega ao PricingService para logica unificada.

    Regras:
    1. Agrupamento por (data_atendimento, cidade)
    2. 1o chamado do lote: valor cheio
    3. Demais: valor adicional
    4. Excecoes: paga_tecnico=False, pagamento_integral=True
    """
    return PricingService.processar_fechamento(chamados, tecnico)


def garantir_custo_atribuido(chamados, tecnico):
    """
    DEPRECATED (2026-01): O custo deve ser congelado na APROVAÇÃO, não no pagamento.
    
    Esta função agora apenas VALIDA a integridade.
    Lança exceção se algum chamado aprovado não tiver custo definido.
    
    O recálculo foi removido para eliminar "Late Binding" de custos.
    Se um chamado chegar aqui sem custo_atribuido, é um BUG no fluxo de aprovação.
    
    Args:
        chamados: Lista de Chamado a verificar
        tecnico: Tecnico responsavel (não utilizado, mantido para compatibilidade)

    Returns:
        int: Sempre 0 (nenhum recálculo feito)
        
    Raises:
        ValueError: Se algum chamado não tiver custo_atribuido definido
    """
    for chamado in chamados:
        if chamado.custo_atribuido is None:
            raise ValueError(
                f"INTEGRIDADE VIOLADA: Chamado {chamado.id} (código: {chamado.codigo_chamado}) "
                f"está aprovado mas sem custo_atribuido. "
                f"O custo deveria ter sido congelado na aprovação (aprovar_batch). "
                f"Isso é um bug no fluxo ou dado legado. "
                f"Corrija manualmente ou re-aprove o lote."
            )
    
    return 0  # Nenhum recálculo feito - integridade OK

# Função isolada (fora da classe) para rodar em background
def task_processar_lote(tecnicos_ids, inicio_str, fim_str):
    """
    Processa pagamentos em lote em background com auditoria (JobRun).
    
    WARNING: JOB BOUNDARY - DO NOT CALL FROM WITHIN A TRANSACTION.
    Esta função gerencia seu próprio ciclo de vida (commit/rollback).
    Deve ser executada apenas como Task isolada (Background Job).
    """
    from flask import current_app
    from src.models import JobRun
    import json
    
    # Log inicial
    logger.info(f"[LOTE] Iniciando processamento background para {len(tecnicos_ids)} tecnicos.")
    
    # Verificar se temos app_context
    try:
        app = current_app._get_current_object()
        has_context = True
    except RuntimeError:
        has_context = False
        from src import create_app
        app = create_app()
    
    def _run_task():
        # 1. Criar JobRun (Audit)
        job = JobRun(
            job_name='financeiro_lote',
            status='RUNNING',
            total_items=len(tecnicos_ids),
            metadata_json=json.dumps({
                'tecnicos_ids': tecnicos_ids,
                'inicio': inicio_str,
                'fim': fim_str
            })
        )
        db.session.add(job)
        db.session.commit() # Commit inicial para gerar ID
        
        job_id = job.id
        logger.info(f"[LOTE] JobRun #{job_id} criado.")

        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
        
        count_success = 0
        count_error = 0
        log_messages = []
        
        try:
            for t_id in tecnicos_ids:
                try:
                    # Refresh Job status (keep connection alive)
                    # job = JobRun.query.get(job_id) # Opcional se for muito longo

                    tecnico = Tecnico.query.get(t_id)
                    if not tecnico: 
                        log_messages.append(f"Skipped: Tecnico {t_id} not found")
                        continue
                        
                    if tecnico.tecnico_principal_id:
                        log_messages.append(f"Skipped: Tecnico {t_id} is sub (Subordinated to {tecnico.tecnico_principal_id})")
                        continue

                    # Gate Unificado: Só processa APROVADOS
                    chamados_proprios = tecnico.chamados.filter(
                        Chamado.status_chamado == 'Concluído',
                        Chamado.status_validacao == 'Aprovado',
                        Chamado.pago == False,
                        Chamado.pagamento_id == None,
                        Chamado.data_atendimento >= inicio,
                        Chamado.data_atendimento <= fim
                    ).all()
                    
                    chamados_sub = []
                    for sub in tecnico.sub_tecnicos:
                        chamados_sub.extend(sub.chamados.filter(
                            Chamado.status_chamado == 'Concluído',
                            Chamado.status_validacao == 'Aprovado',
                            Chamado.pago == False,
                            Chamado.pagamento_id == None,
                            Chamado.data_atendimento >= inicio,
                            Chamado.data_atendimento <= fim
                        ).all())
                        
                    chamados_todos = chamados_proprios + chamados_sub
                    
                    if not chamados_todos:
                        log_messages.append(f"Skipped: Tecnico {tecnico.nome} (ID {t_id}) has no pending approved calls")
                        continue

                    # Processar Custos (Agrupamento por Lote)
                    processar_custos_chamados(chamados_todos, tecnico)

                    # P3: INTEGRIDADE - Garantir que todos tenham custo_atribuido
                    recalc = garantir_custo_atribuido(chamados_todos, tecnico)
                    if recalc > 0:
                        log_messages.append(f"Warn: Tecnico {t_id} had {recalc} calls recalculated")

                    pagamento = Pagamento(
                        tecnico_id=tecnico.id,
                        periodo_inicio=inicio,
                        periodo_fim=fim,
                        valor_por_atendimento=tecnico.valor_por_atendimento,
                        status_pagamento='Pendente',
                        observacoes='Processado via Lote (Economia de Escala)'
                    )
                    db.session.add(pagamento)
                    db.session.flush()
                    
                    for c in chamados_todos:
                        c.pagamento_id = pagamento.id
                        c.pago = False 
                        db.session.add(c)
                    
                    # COMMIT INDIVIDUAL por Tecnico
                    db.session.commit()
                    count_success += 1
                    
                except Exception as e_inner:
                    count_error += 1
                    error_msg = f"Error processing Tecnico {t_id}: {str(e_inner)}"
                    log_messages.append(error_msg)
                    logger.error(f"[LOTE] {error_msg}")
                    db.session.rollback()
                    continue
            
            # Finalizar Job com Sucesso (ou Parcial)
            job = JobRun.query.get(job_id)
            job.end_time = datetime.utcnow()
            job.success_count = count_success
            job.error_count = count_error
            
            if count_error == 0:
                job.status = 'COMPLETED'
            elif count_success > 0:
                job.status = 'PARTIAL_SUCCESS'
            else:
                job.status = 'FAILED'
                
            job.log_text = "\n".join(log_messages)
            db.session.commit()
            
            logger.info(f"[LOTE] Job #{job_id} finished: {job.status}. Success: {count_success}, Errors: {count_error}")

        except Exception as e_fatal:
            db.session.rollback()
            logger.exception(f"[LOTE] FATAL Job #{job_id}: {str(e_fatal)}")
            
            # Tentar salvar status de erro no Job
            try:
                job = JobRun.query.get(job_id)
                job.end_time = datetime.utcnow()
                job.status = 'CRASHED'
                job.error_count = count_error + 1
                job.log_text = (job.log_text or "") + f"\nFATAL CRASH: {str(e_fatal)}"
                db.session.commit()
            except:
                logger.error("Could not update JobRun status after crash.")

    # Executar com contexto apropriado
    if has_context:
        _run_task()
    else:
        with app.app_context():
            _run_task()

class FinanceiroService:
    @staticmethod
    def calcular_projecao_mensal():
        hoje = datetime.now()
        ano = hoje.year
        mes = hoje.month
        
        # Último dia do mês
        _, ult_dia = calendar.monthrange(ano, mes)
    def calcular_projecao_mensal(tecnico_id=None):
        from decimal import Decimal
        """
        Calcula projecao de custos do mes atual (Chamados ja realizados).
        Retorna totais somados (Custos ja atribuidos).
        """
        data_inicio = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        query = Chamado.query.filter(
            Chamado.data_atendimento >= data_inicio,
            Chamado.status_chamado == 'Concluído'
        )
        
        if tecnico_id:
            query = query.filter(Chamado.tecnico_id == tecnico_id)
            
        chamados = query.all()
        
        total_atual = Decimal('0.00')
        qnt_atual = 0
        
        for c in chamados:
            # Soma custo ja atribuido (ou 0 se pendente)
            # Agora usando Decimal para evitar drift de float
            custo = Decimal(str(c.custo_atribuido or '0.00'))
            total_atual += custo
            qnt_atual += 1
            
        return {
            'total_atual': float(total_atual), # Frontend expects float/json
            'qnt_atual': qnt_atual,
            'media_por_chamado': float(total_atual / qnt_atual) if qnt_atual > 0 else 0.0
        }

    @staticmethod
    def get_lucro_real_mensal(ano, mes):
        from decimal import Decimal
        """
        Calcula Receita Real (Confirmada) - Custo Real (Pagamentos Gerados).
        Baseado em Datas de Competência (Atendimento).
        """
        from sqlalchemy import extract
        
        # Filtra chamados do mes
        chamados = Chamado.query.filter(
            extract('year', Chamado.data_atendimento) == ano,
            extract('month', Chamado.data_atendimento) == mes,
            Chamado.status_chamado == 'Concluído'
        ).all()
        
        receita_total = Decimal('0.00')
        custo_total = Decimal('0.00')
        qnt = 0
        
        for c in chamados:
            # Receita: Soma valor_receita_total (Serviço + Peça)
            receita = Decimal(str(c.valor_receita_total or '0.00'))
            
            # Custo: Soma custo_atribuido (Mão de obra) + custo_peca (Materiais)
            custo_mo = Decimal(str(c.custo_atribuido or '0.00'))
            custo_peca = Decimal(str(c.custo_peca or '0.00'))
            
            receita_total += receita
            custo_total += (custo_mo + custo_peca)
            qnt += 1
            
        resultado_liquido = receita_total - custo_total
        margem = (resultado_liquido / receita_total * 100) if receita_total > 0 else Decimal('0.00')
        
        return {
            'periodo': f"{mes}/{ano}",
            'receita_bruta': float(receita_total),
            'custo_total': float(custo_total),
            'lucro_liquido': float(resultado_liquido),
            'margem_percent': float(round(margem, 1)),
            'quantidade_chamados': qnt
        }

    @staticmethod
    def get_pendentes_stats():
        """
        Retorna a quantidade de pagamentos pendentes
        """
        return Pagamento.query.filter_by(status_pagamento='Pendente').count()

    @staticmethod
    def get_all(filters=None):
        query = Pagamento.query
        
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter_by(tecnico_id=filters['tecnico_id'])
            if filters.get('status'):
                query = query.filter_by(status_pagamento=filters['status'])
                
        return query.order_by(Pagamento.data_criacao.desc()).all()

    @staticmethod
    def get_by_id(id):
        return Pagamento.query.get_or_404(id)

    @staticmethod
    def gerar_pagamento(data):
        """
        Gera pagamento para um técnico.
        
        REFATORADO (2026-01): Adicionado filtro status_validacao=='Aprovado'
        para alinhar com task_processar_lote e fechar brecha de governança.
        """
        tecnico_id = data.get('tecnico_id')
        tecnico = Tecnico.query.get(tecnico_id)
        
        if not tecnico:
            return None, "Técnico não encontrado."

        if tecnico.tecnico_principal_id is not None:
            return None, f"Este técnico é subordinado a {tecnico.tecnico_principal.nome}. Gere o pagamento para o chefe."
            
        # P0: UNIFICAR GATE - Exigir status_validacao == 'Aprovado'
        chamados_proprios = tecnico.chamados.filter(
            Chamado.status_chamado == 'Concluído',
            Chamado.status_validacao == 'Aprovado',  # P0: Gate unificado
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ).all()
        
        chamados_sub = []
        for sub in tecnico.sub_tecnicos:
            chamados_sub.extend(sub.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.status_validacao == 'Aprovado',  # P0: Gate unificado
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).all())
            
        chamados_todos = chamados_proprios + chamados_sub
        
        if not chamados_todos:
            return None, "Não há chamados APROVADOS pendentes para este técnico ou afiliados."
            
        dates = [c.data_atendimento for c in chamados_todos]
        periodo_inicio = min(dates)
        periodo_fim = max(dates)

        # Processar Custos (Agrupamento por Lote)
        processar_custos_chamados(chamados_todos, tecnico)

        # P3: INTEGRIDADE - Garantir que todos tenham custo_atribuido
        garantir_custo_atribuido(chamados_todos, tecnico)

        # Check for immediate payment flag (handle boolean or string 'on')
        mark_flag = data.get('mark_as_paid')
        is_paid = mark_flag in [True, 'on', 'true', '1']
        
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pago' if is_paid else 'Pendente',
            data_pagamento=datetime.now() if is_paid else None,
            observacoes='Gerado manualmente' + (' (Pago Imediatamente)' if is_paid else '')
        )
        
        db.session.add(pagamento)
        db.session.flush() 
        
        for c in chamados_todos:
            c.pago = is_paid 
            c.pagamento_id = pagamento.id
            
        # db.session.commit() # REMOVIDO: Caller deve commitar
        return pagamento, None

    @staticmethod
    def marcar_como_pago(id, observacoes=None):
        pagamento = Pagamento.query.get_or_404(id)
        pagamento.status_pagamento = 'Pago'
        pagamento.data_pagamento = datetime.now()
        if observacoes:
            pagamento.observacoes = observacoes
            
        # Mark all chamados as paid
        for chamado in pagamento.chamados_incluidos:
            chamado.pago = True
            
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return pagamento

    @staticmethod
    def criar_lancamento(data):
        """
        TODO: FIXME - METODO DESABILITADO (2025)
        ========================================
        Este metodo foi DESABILITADO porque:
        1. Referencia classe 'Lancamento' que NAO EXISTE em models.py
        2. Referencia atributo 'tecnico.saldo_atual' que NAO EXISTE no schema
        3. A arquitetura atual usa Chamado.custo_atribuido em vez de Ledger

        Para reativar, seria necessario:
        - Criar model Lancamento com campos: tecnico_id, tipo, valor, data, descricao
        - Adicionar campo saldo_atual ao model Tecnico
        - Criar migrations para o banco de dados

        Alternativa atual: Use PricingService para calculos de custo.
        """
        import warnings
        warnings.warn(
            "criar_lancamento() esta DESABILITADO. "
            "Use PricingService.calcular_custo_tempo_real() em vez disso.",
            DeprecationWarning,
            stacklevel=2
        )
        return None

        # =====================================================================
        # CODIGO ORIGINAL COMENTADO - NAO REMOVER (referencia futura)
        # =====================================================================
        # lancamento = Lancamento(
        #     tecnico_id=data.get('tecnico_id'),
        #     tipo=data.get('tipo'),
        #     valor=float(data.get('valor')),
        #     data=datetime.strptime(data.get('data'), '%Y-%m-%d').date() if data.get('data') else datetime.now().date(),
        #     descricao=data.get('descricao')
        # )
        #
        # # Atualizar Saldo do Tecnico
        # tecnico = Tecnico.query.get(lancamento.tecnico_id)
        # if lancamento.tipo in ['CREDITO_SERVICO', 'BONUS', 'REEMBOLSO']:
        #     tecnico.saldo_atual += float(lancamento.valor)
        # elif lancamento.tipo in ['DEBITO_PAGAMENTO', 'ADIANTAMENTO', 'MULTA']:
        #     tecnico.saldo_atual -= float(lancamento.valor)
        #
        # db.session.add(lancamento)
        # db.session.commit()
        # return lancamento

    @staticmethod
    def registrar_credito_servico(chamado):
        """
        Calcula o valor do servico (considerando regras de lote dia/cidade).
        Deve ser chamado quando o chamado e APROVADO.

        REFATORADO (2025): Usa PricingService para calculo unificado.
        """
        tecnico = chamado.tecnico
        if not tecnico and chamado.tecnico_id:
            tecnico = Tecnico.query.get(chamado.tecnico_id)

        if not tecnico:
            return None

        # USAR PRICING SERVICE para calculo em tempo real
        custo_calculado = PricingService.calcular_custo_tempo_real(chamado, tecnico)

        chamado.custo_atribuido = custo_calculado

        # NOTE: Ledger (Lancamento) removed. Payment is calculated on demand via Chamado.custo_atribuido.
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return None

    @staticmethod
    def realizar_pagamento_conta_corrente(tecnico_id, valor, observacao=None):
        """
        TODO: FIXME - METODO DESABILITADO (2025)
        ========================================
        Este metodo foi DESABILITADO porque:
        1. Dependia da classe 'Lancamento' que NAO EXISTE
        2. Sistema de conta corrente/ledger foi removido
        3. Pagamentos agora sao controlados via Pagamento + Chamado.custo_atribuido

        Alternativa atual: Use FinanceiroService.gerar_pagamento() para criar pagamentos.
        """
        import warnings
        warnings.warn(
            "realizar_pagamento_conta_corrente() esta DESABILITADO. "
            "Use gerar_pagamento() em vez disso.",
            DeprecationWarning,
            stacklevel=2
        )
        return None

    @staticmethod
    def gerar_pagamento_lote(data):
        """
        Agora este método apenas dispara a tarefa e retorna imediatamente.
        """
        tecnicos_ids = data.get('tecnicos_ids', [])
        periodo_inicio = data.get('periodo_inicio')
        periodo_fim = data.get('periodo_fim')
        
        # Dispara a tarefa em background (Fire and Forget)
        executor.submit(task_processar_lote, tecnicos_ids, periodo_inicio, periodo_fim)
        
        # Retorna sucesso imediato (0 erros, pois erros serão logados no console/banco depois)
        return len(tecnicos_ids), []

    @staticmethod
    def calcular_previa_fechamento(data_inicio, data_fim):
        """
        Calcula prévia de fechamento por período.
        
        REFATORADO (2026-01): Extraído de financeiro_routes.py para eliminar Fat Controller.
        
        Args:
            data_inicio: date - Data inicial do período
            data_fim: date - Data final do período
            
        Returns:
            List[dict]: Lista de técnicos com valores previstos para fechamento
        """
        from sqlalchemy import func
        from src.models import db
        
        # OTIMIZACAO: Query SQL agregada em vez de N+1
        val_expr = func.coalesce(Chamado.custo_atribuido, 0)

        result = db.session.query(
            Tecnico.id,
            Tecnico.nome,
            func.count(Chamado.id).label('qtd_chamados'),
            func.sum(val_expr).label('total_previsto')
        ).join(
            Chamado, Tecnico.id == Chamado.tecnico_id
        ).filter(
            Tecnico.status == 'Ativo',
            Chamado.status_chamado == 'Concluído',
            Chamado.status_validacao == 'Aprovado',  # P0: Gate unificado
            Chamado.pago == False,
            Chamado.pagamento_id == None,
            Chamado.data_atendimento >= data_inicio,
            Chamado.data_atendimento <= data_fim
        ).group_by(
            Tecnico.id
        ).having(
            func.count(Chamado.id) > 0
        ).all()

        tecnicos_display = []
        for row in result:
            tecnicos_display.append({
                'id': row[0],
                'id_tecnico': f"T-{str(row[0]).zfill(3)}",
                'nome': row[1],
                'qtd_chamados': row[2],
                'total_previsto': float(row[3] or 0)
            })

        return tecnicos_display
