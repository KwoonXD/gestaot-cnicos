from datetime import datetime
import calendar
from sqlalchemy import func
# Importamos o executor global que criamos acima
from src import executor, db 
from src.models import Chamado, Pagamento, Tecnico, Lancamento

# Função isolada (fora da classe) para rodar em background
def task_processar_lote(tecnicos_ids, inicio_str, fim_str):
    print(f"--> Iniciando processamento background para {len(tecnicos_ids)} técnicos.")
    
    # É necessário recriar o contexto se não for thread-local, mas o Flask-Executor cuida disso.
    # Convertemos strings de volta para data
    inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
    fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
    
    count = 0
    errors = []
    
    try:
        for t_id in tecnicos_ids:
            tecnico = Tecnico.query.get(t_id)
            if not tecnico: continue
                
            # Se for um sub-técnico (tem principal), pular (será processado pelo principal)
            if tecnico.tecnico_principal_id:
                continue

            chamados_proprios = tecnico.chamados.filter(
                Chamado.status_chamado == 'Concluído',
                Chamado.pago == False,
                Chamado.pagamento_id == None,
                Chamado.data_atendimento >= inicio,
                Chamado.data_atendimento <= fim
            ).all()
            
            chamados_sub = []
            for sub in tecnico.sub_tecnicos:
                chamados_sub.extend(sub.chamados.filter(
                    Chamado.status_chamado == 'Concluído',
                    Chamado.pago == False,
                    Chamado.pagamento_id == None,
                    Chamado.data_atendimento >= inicio,
                    Chamado.data_atendimento <= fim
                ).all())
                
            chamados_todos = chamados_proprios + chamados_sub
            
            if not chamados_todos:
                continue
                
            pagamento = Pagamento(
                tecnico_id=tecnico.id,
                periodo_inicio=inicio,
                periodo_fim=fim,
                valor_por_atendimento=tecnico.valor_por_atendimento,
                status_pagamento='Pendente',
                observacoes='Processado via Lote em Background'
            )
            db.session.add(pagamento)
            db.session.flush()
            
            for c in chamados_todos:
                c.pagamento_id = pagamento.id
            
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
        
        # Query total value of Chamados in current month
        # Assuming we count based on 'data_atendimento' or 'data_criacao'. 
        # User said "total_gasto", usually related to completed services.
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
            
        # Get unpaid completed chamados (not yet assigned to a payment) for the Tecnico
        chamados_proprios = tecnico.chamados.filter(
            Chamado.status_chamado == 'Concluído', 
            Chamado.pago == False,
            Chamado.pagamento_id == None
        ).all()
        
        # Get unpaid completed chamados from Sub-Tecnicos
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
            
        # Determine dates based on all calls
        dates = [c.data_atendimento for c in chamados_todos]
        periodo_inicio = min(dates)
        periodo_fim = max(dates)
            
        pagamento = Pagamento(
            tecnico_id=tecnico_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_por_atendimento=tecnico.valor_por_atendimento,
            status_pagamento='Pendente'
        )
        
        db.session.add(pagamento)
        db.session.flush() # get ID
        
        # Link all chamados to this payment
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
