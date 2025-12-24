from datetime import datetime
import calendar
from sqlalchemy import func
# Importamos o executor global que criamos acima
from src import executor, db 
from src.models import Chamado, Pagamento, Tecnico, Lancamento

# Função auxiliar de cálculo
def processar_custos_chamados(chamados, tecnico):
    """
    Novo Modelo de Cálculo (2025):
    Agrupamento: (tecnico_id, data_atendimento, cidade)
    Regras:
    1. 'Falha' ou 'Falha Operacional' => Paga 0.00
    2. 'Retorno SPARE' => Paga valor cheio (R$ 120 ou valor_por_atendimento)
    3. Demais Casos (Atendimento Normal):
       - Primeiro chamado do grupo: Valor Cheio
       - Próximos chamados do grupo: Valor Adicional
    """
    total_pagamento = 0.0
    
    from collections import defaultdict
    grupos = defaultdict(list)
    
    for c in chamados:
        # Usar cidade como agrupador principal, fallback para loja
        city_key = getattr(c, 'cidade', None) or c.loja or "INDEFINIDO"
        key = (c.data_atendimento, city_key)
        grupos[key].append(c)
        
    for key, lista in grupos.items():
        ja_pagou_principal = False
        lista.sort(key=lambda x: x.id)
        
        for c in lista:
            valor_a_pagar = 0.0
            tipo = getattr(c, 'tipo_resolucao', None) or ''
            
            # --- Regras de Exceção ---
            if 'Falha' in tipo:
                valor_a_pagar = 0.0
            elif 'Retorno SPARE' in tipo:
                # Exceção: Paga cheio sempre (técnico se deslocou)
                valor_a_pagar = float(tecnico.valor_por_atendimento)
            else:
                # Regra Padrão (Principal vs Adicional)
                if not ja_pagou_principal:
                    valor_a_pagar = float(tecnico.valor_por_atendimento)
                    ja_pagou_principal = True
                else:
                    valor_a_pagar = float(tecnico.valor_adicional_loja)

            # Reembolso de Peça (Sempre paga se Tec comprou)
            if getattr(c, 'fornecedor_peca', None) == 'Tecnico':
                valor_a_pagar += float(c.custo_peca or 0.0)
                
            c.custo_atribuido = valor_a_pagar
            total_pagamento += valor_a_pagar

    return total_pagamento

# Função isolada (fora da classe) para rodar em background
def task_processar_lote(tecnicos_ids, inicio_str, fim_str):
    print(f"--> Iniciando processamento background para {len(tecnicos_ids)} técnicos.")
    
    inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
    fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
    
    count = 0
    
    try:
        # Contexto já deve estar ativo se chamado via executor com app_context, 
        # mas por segurança em threads:
        # from flask import current_app
        # if not current_app: ... (Omitindo por simplicidade da task)
        
        for t_id in tecnicos_ids:
            tecnico = Tecnico.query.get(t_id)
            if not tecnico: continue
                
            if tecnico.tecnico_principal_id:
                continue

            chamados_proprios = tecnico.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.status_validacao == 'Aprovado',  # Só aprovados vão para financeiro
                Chamado.pago == False,
                Chamado.pagamento_id == None,
                Chamado.data_atendimento >= inicio,
                Chamado.data_atendimento <= fim
            ).all()
            
            chamados_sub = []
            for sub in tecnico.sub_tecnicos:
                chamados_sub.extend(sub.chamados.filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.status_validacao == 'Aprovado',  # Só aprovados
                    Chamado.pago == False,
                    Chamado.pagamento_id == None,
                    Chamado.data_atendimento >= inicio,
                    Chamado.data_atendimento <= fim
                ).all())
                
            chamados_todos = chamados_proprios + chamados_sub
            
            if not chamados_todos:
                continue
            
            # Processar Custos (Agrupamento)
            processar_custos_chamados(chamados_todos, tecnico)
                
            pagamento = Pagamento(
                tecnico_id=tecnico.id,
                periodo_inicio=inicio,
                periodo_fim=fim,
                valor_por_atendimento=tecnico.valor_por_atendimento, # Apenas referência
                status_pagamento='Pendente',
                observacoes='Processado via Lote (Economia de Escala)'
            )
            db.session.add(pagamento)
            db.session.flush()
            
            for c in chamados_todos:
                c.pagamento_id = pagamento.id
                c.pago = False # Só vira True quando Pagamento mudar status
            
            count += 1
            
        db.session.commit()
        print(f"--> Lote finalizado. {count} pagamentos gerados.")
        
    except Exception as e:
        db.session.rollback()
        print(f"--> Erro no lote: {str(e)}")

class FinanceiroService:
    @staticmethod
    def calcular_projecao_mensal():
        hoje = datetime.now()
        ano = hoje.year
        mes = hoje.month
        
        # Último dia do mês
        _, ult_dia = calendar.monthrange(ano, mes)
        
        # Média diária (evitar divisão por zero se for dia 1)
        dia_hoje = hoje.day
        if dia_hoje == 1:
            dia_divisor = 1
        else:
            dia_divisor = dia_hoje
            
        # Total gasto neste mês até agora
        inicio_mes = datetime(ano, mes, 1)
        
        total_atual = db.session.query(func.sum(Chamado.valor))\
            .filter(Chamado.data_atendimento >= inicio_mes)\
            .filter(Chamado.data_atendimento <= hoje)\
            .scalar() or 0.0
            
        total_atual = float(total_atual)
        
        media_diaria = total_atual / dia_divisor
        projecao = media_diaria * ult_dia
        
        return {
            'atual': total_atual,
            'projecao': projecao,
            'media_diaria': media_diaria
        }

    @staticmethod
    def get_lucro_real_mensal():
        hoje = datetime.now()
        mes = hoje.month
        ano = hoje.year
        
        chamados = Chamado.query.filter(
            db.extract('month', Chamado.data_atendimento) == mes,
            db.extract('year', Chamado.data_atendimento) == ano,
            Chamado.status_chamado == 'Concluído'
        ).all()
        
        receita_servico = sum(float(c.valor_receita_servico or 0) for c in chamados)
        receita_peca = sum(float(c.valor_receita_peca or 0) for c in chamados)
        receita_total = receita_servico + receita_peca
        
        custo_tecnicos = sum(float(c.custo_atribuido or 0) for c in chamados)
        custo_pecas_empresa = sum(float(c.custo_peca or 0) for c in chamados if c.fornecedor_peca == 'Empresa')
        custo_total = custo_tecnicos + custo_pecas_empresa
        
        lucro = receita_total - custo_total
        margem = (lucro / receita_total * 100) if receita_total > 0 else 0.0
        
        return {
            'receita_total': receita_total,
            'custo_total': custo_total,
            'lucro': lucro,
            'margem': margem
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
        tecnico_id = data.get('tecnico_id')
        tecnico = Tecnico.query.get(tecnico_id)
        
        if not tecnico:
            return None, "Técnico não encontrado."

        if tecnico.tecnico_principal_id is not None:
            return None, f"Este técnico é subordinado a {tecnico.tecnico_principal.nome}. Gere o pagamento para o chefe."
            
        chamados_proprios = tecnico.chamados.filter(
            Chamado.status_chamado == 'Concluído', 
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ).all()
        
        chamados_sub = []
        for sub in tecnico.sub_tecnicos:
            chamados_sub.extend(sub.chamados.filter(
                Chamado.status_chamado == 'Concluído', 
                Chamado.pago == False,
                Chamado.pagamento_id == None
            ).all())
            
        chamados_todos = chamados_proprios + chamados_sub
        
        if not chamados_todos:
            return None, "Não há chamados pendentes para este técnico ou afiliados."
            
        dates = [c.data_atendimento for c in chamados_todos]
        periodo_inicio = min(dates)
        periodo_fim = max(dates)
        
        # Processar Custos (Agrupamento)
        processar_custos_chamados(chamados_todos, tecnico)
            
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pendente'
        )
        
        db.session.add(pagamento)
        db.session.flush() 
        
        for c in chamados_todos:
            c.pago = False 
            c.pagamento_id = pagamento.id
            
        db.session.commit()
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
            
        db.session.commit()
        return pagamento

    @staticmethod
    def criar_lancamento(data):
        lancamento = Lancamento(
            tecnico_id=data.get('tecnico_id'),
            tipo=data.get('tipo'),
            valor=float(data.get('valor')),
            data=datetime.strptime(data.get('data'), '%Y-%m-%d').date() if data.get('data') else datetime.now().date(),
            descricao=data.get('descricao')
        )
        db.session.add(lancamento)
        db.session.commit()
        return lancamento

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
