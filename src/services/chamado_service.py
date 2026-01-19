
from ..models import db, Chamado, Tecnico, CatalogoServico, ItemLPU, Cliente, TecnicoStock
from datetime import datetime
from flask_login import current_user
from .audit_service import AuditService
from .pricing_service import PricingService
from .stock_service import StockService
import uuid
import re
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func

# Constantes de Negocio (Importadas do PricingService para compatibilidade)
# Constantes de Negocio (Importadas do PricingService para compatibilidade)
from .pricing_service import HORAS_FRANQUIA_PADRAO
from .pricing_service import VALOR_HORA_EXTRA_DEFAULT
from .pricing_service import VALOR_ATENDIMENTO_BASE
from .pricing_service import VALOR_ADICIONAL_LOJA
from .pricing_service import ChamadoInput

class ChamadoService:

    @staticmethod
    def extract_fsa_code(input_str):
        """
        Extrai o código FSA de uma URL do Jira ou retorna a string limpa.
        Ex: 'https://delfia.atlassian.net/browse/FSA-5050' -> 'FSA-5050'
        Ex: 'FSA-5050' -> 'FSA-5050'
        Ex: '  fsa-123  ' -> 'FSA-123'
        """
        if not input_str:
            return None
        
        text = str(input_str).strip()
        
        # Se contém "browse/", pega a última parte
        if 'browse/' in text:
            parts = text.split('browse/')
            text = parts[-1].strip('/')
        
        # Remove caracteres inválidos e retorna uppercase se parecer um código
        text = text.strip()
        if text:
            # Extrai padrão FSA-XXXX ou similar
            match = re.search(r'([A-Za-z]+-\d+)', text)
            if match:
                return match.group(1).upper()
        
        return text.upper() if text else None

    @staticmethod
    def calculate_hours_worked(hora_inicio, hora_fim):
        """
        Calcula horas trabalhadas a partir de strings "HH:MM".
        DELEGADO ao PricingService para manter logica unificada.
        """
        return PricingService.calculate_hours_worked(hora_inicio, hora_fim)

    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        # Eager load Tecnico to avoid N+1
        query = Chamado.query.options(joinedload(Chamado.tecnico))
        
        # Join explicitly for filtering if needed
        query = query.join(Tecnico)
        
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter(Chamado.tecnico_id == int(filters['tecnico_id']))
            if filters.get('status'):
                query = query.filter(Chamado.status_chamado == filters['status'])
            if filters.get('status_validacao'):
                # Handle list or single value
                val = filters['status_validacao']
                if isinstance(val, list):
                    query = query.filter(Chamado.status_validacao.in_(val))
                else:
                    query = query.filter(Chamado.status_validacao == val)
            if filters.get('tipo'):
                query = query.filter(Chamado.tipo_servico == filters['tipo'])
            if filters.get('pago'):
                if filters['pago'] == 'sim':
                    query = query.filter(Chamado.pago == True)
                elif filters['pago'] == 'nao':
                    query = query.filter(Chamado.pago == False)
            if filters.get('search'):
                s = filters['search']
                query = query.filter(
                    or_(
                        Chamado.codigo_chamado.ilike(f"%{s}%"),
                        Tecnico.nome.ilike(f"%{s}%"),
                        Chamado.loja.ilike(f"%{s}%")
                    )
                )
        
        # Retorna o objeto Pagination, não a lista (.all)
        return query.order_by(Chamado.data_atendimento.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def get_relatorio_faturamento(cliente_id, data_inicio, data_fim, estado=None):
        from decimal import Decimal
        """
        Gera relatório financeiro de fechamento por contrato.
        Filtra por Cliente (obrigatório), Range de Datas e Estado (opcional).
        """
        # Base query joining necessary tables
        query = Chamado.query.join(Chamado.catalogo_servico).join(CatalogoServico.cliente)
        query = query.filter(Cliente.id == int(cliente_id))
        
        # Date filter
        query = query.filter(Chamado.data_atendimento >= data_inicio)
        query = query.filter(Chamado.data_atendimento <= data_fim)
        
        # Join tecnico for State info
        query = query.join(Chamado.tecnico)
        
        # State filter (Optional)
        if estado:
            query = query.filter(Tecnico.estado == estado)
            
        chamados = query.order_by(Chamado.data_atendimento).all()
        
        itens = []
        total_geral = Decimal('0.00')
        
        for c in chamados:
            # Confia no valor calculado na criação (já considera Retorno=0 se regra aplicada)
            # Mas como segurança, se for nulo, usa 0
            valor_final = Decimal(str(c.valor_receita_total or '0.00'))
            
            nome_servico = c.catalogo_servico.nome if c.catalogo_servico else c.tipo_servico
            
            itens.append({
                'data': c.data_atendimento.strftime('%d/%m/%Y'),
                'codigo': c.codigo_chamado or f"ID-{c.id}",
                'cidade': c.cidade,
                'estado': c.tecnico.estado if c.tecnico else 'PB', # Default PB is fallback
                'servico': nome_servico,
                'valor': float(valor_final) # JSON needs float, but calc is Decimal
            })
            total_geral += valor_final
            
        return {
            'itens': itens,
            'total_geral': float(total_geral),
            'periodo': f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
        }

    @staticmethod
    def create_multiplo(logistica, fsas):
        from decimal import Decimal
        """
        Cria chamados em lote, aplica regras de precificacao (Primeiro vs Adicional)
        e baixa estoque automaticamente.

        REFATORADO (2025): Usa PricingService para calculo unificado de custos.
        """
        criados = []
        batch_id = str(uuid.uuid4())  # Gera ID unico para o lote

        try:
            if not logistica.get('tecnico_id'):
                raise ValueError("Tecnico nao informado.")

            # Converte string de data '2025-01-01' para objeto date
            data_atendimento = datetime.strptime(logistica['data_atendimento'], '%Y-%m-%d').date()
        except ValueError:
            data_atendimento = datetime.now().date()

        # 1. Pre-fetch Servicos
        service_ids = []
        for f in fsas:
            try:
                if f.get('catalogo_servico_id'):
                    service_ids.append(int(f.get('catalogo_servico_id')))
            except (ValueError, TypeError):
                continue

        services_map = {s.id: s for s in CatalogoServico.query.filter(CatalogoServico.id.in_(service_ids)).all()}

        # 2. USAR PRICING SERVICE para calcular custos (Logica Unificada)
        resultados_pricing = PricingService.processar_criacao_multipla(
            fsas=fsas,
            logistica=logistica,
            services_map=services_map
        )

        # 3. Criar chamados com valores calculados pelo PricingService
        for resultado in resultados_pricing:
            fsa = resultado['fsa']

            # Valores calculados pelo PricingService (agora ja vêm como Decimal ou float dependendo do PricingService)
            # Garantir casting seguro
            def to_d(val): return Decimal(str(val or '0.00'))

            valor_receita_servico = to_d(resultado['valor_receita_servico'])
            valor_receita_total = to_d(resultado['valor_receita_total'])
            custo_atribuido = to_d(resultado['custo_atribuido'])
            
            horas_trabalhadas = to_d(resultado['horas_trabalhadas'])
            is_adicional = resultado['is_adicional']

            # Inicializa valores de peça
            peca_nome = ""
            custo_peca = Decimal('0.00')
            valor_receita_peca = Decimal('0.00')
            fornecedor = fsa.get('fornecedor_peca', 'Empresa')

            # Pre-fetch nome da peça e valor de receita (usando tabela de precos por contrato)
            if fsa.get('peca_id'):
                item = ItemLPU.query.get(fsa['peca_id'])
                if item:
                    peca_nome = item.nome

                    # Obter cliente_id do CatalogoServico para buscar preco personalizado
                    servico = services_map.get(int(fsa['catalogo_servico_id'])) if fsa.get('catalogo_servico_id') else None
                    cliente_id = servico.cliente_id if servico else None

                    # Buscar valor de receita da peca usando tabela de precos por contrato
                    # PricingService.get_valor_peca agora retorna Decimal
                    valor_receita_peca = PricingService.get_valor_peca(cliente_id, item.id) if cliente_id else Decimal(str(item.valor_receita or '0.00'))
                    
                    # Se Fornecedor = Tecnico -> Custo informado manualmente
                    if fornecedor == 'Tecnico':
                        custo_peca = Decimal(str(fsa.get('custo_peca', 0) or '0.00'))

            # Adicionar receita da peca ao total
            valor_receita_total = valor_receita_servico + valor_receita_peca

            # Totais
            valor_legacy = valor_receita_total  # Campo 'valor' mantém compatibilidade

            # Cria o Chamado (sem custo de peça ainda se for da Empresa)
            novo_chamado = Chamado(
                tecnico_id=int(logistica['tecnico_id']),
                horas_trabalhadas=horas_trabalhadas,
                cidade=logistica['cidade'],
                data_atendimento=data_atendimento,
                observacoes=logistica.get('observacoes'),

                # Dados FSA
                codigo_chamado=fsa['codigo_chamado'],
                catalogo_servico_id=int(fsa['catalogo_servico_id']) if fsa.get('catalogo_servico_id') else None,
                hora_inicio=fsa.get('hora_inicio'),
                hora_fim=fsa.get('hora_fim'),
                is_adicional=is_adicional,

                # Pecas (custo será atualizado após flush se for da Empresa)
                peca_usada=peca_nome,
                custo_peca=custo_peca,
                fornecedor_peca=fornecedor,

                # Financeiro - RECEITA (Calculado pelo PricingService + Preco Contrato)
                valor_receita_servico=valor_receita_servico,
                valor_receita_peca=valor_receita_peca,  # Preco personalizado por contrato
                valor_receita_total=valor_receita_total,
                valor=valor_legacy,  # Legado

                # Financeiro - CUSTO (Calculado pelo PricingService)
                custo_atribuido=custo_atribuido,

                created_by_id=current_user.id,
                status_chamado='Concluído',
                status_validacao='Pendente',
                batch_id=batch_id
            )
            db.session.add(novo_chamado)

            # Flush para obter o ID do chamado (necessário para vincular movimentação)
            db.session.flush()

            # --- INTEGRACAO COM ESTOQUE (Pilar de Custos de Materiais) ---
            # Se peça foi usada e fornecida pela Empresa -> Registrar uso com rastreabilidade
            if fsa.get('peca_id') and fornecedor == 'Empresa':
                try:
                    custo_peca = StockService.registrar_uso_chamado(
                        tecnico_id=int(logistica['tecnico_id']),
                        item_id=int(fsa['peca_id']),
                        chamado_id=novo_chamado.id,
                        user_id=current_user.id,
                        quantidade=1
                    )
                    # Atualizar custo_peca no chamado
                    novo_chamado.custo_peca = custo_peca
                except ValueError as e:
                    # Log warning mas não bloqueia criação do chamado
                    # (peça pode ter sido registrada sem estoque disponível)
                    import logging
                    logging.warning(f"Estoque: {e} - Chamado {novo_chamado.codigo_chamado}")

            criados.append(novo_chamado)

        # db.session.commit() # REMOVIDO: Caller deve commitar
        return criados

    @staticmethod
    def get_grouped_by_batch(filters=None):
        """
        Retorna chamados agrupados por batch_id (lote de atendimento).
        Útil para visualização e geração de links JQL.
        """
        from collections import defaultdict
        from decimal import Decimal
        
        # Eager load tecnico
        query = Chamado.query.options(joinedload(Chamado.tecnico)).filter(Chamado.batch_id.isnot(None))
        
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter(Chamado.tecnico_id == int(filters['tecnico_id']))
            if filters.get('status_validacao'):
                query = query.filter(Chamado.status_validacao == filters['status_validacao'])
        
        chamados = query.order_by(Chamado.data_atendimento.desc(), Chamado.id).all()
        
        # Agrupar por batch_id
        batches = defaultdict(list)
        for c in chamados:
            batches[c.batch_id].append(c)
        
        # Converter para lista de objetos estruturados
        result = []
        for batch_id, chamados_list in batches.items():
            if chamados_list:
                primeiro = chamados_list[0]
                result.append({
                    'batch_id': batch_id,
                    'data': primeiro.data_atendimento,
                    'tecnico': primeiro.tecnico,
                    'cidade': primeiro.cidade,
                    'tipo_resolucao': primeiro.tipo_resolucao,
                    'chamados': chamados_list,
                    'total_receita': sum(Decimal(str(c.valor_receita_total or '0.00')) for c in chamados_list),
                    'codigos_fsa': [c.codigo_chamado for c in chamados_list if c.codigo_chamado]
                })
        
        # Ordenar por data (mais recente primeiro)
        result.sort(key=lambda x: x['data'], reverse=True)
        return result

    @staticmethod
    def get_pending_batches():
        """
        Retorna lotes PENDENTES de validação, otimizado para a Inbox.
        Agrupados por batch_id, com dados pré-formatados para o frontend.
        """
        from collections import defaultdict
        from decimal import Decimal
        
        # Busca apenas pendentes
        chamados = Chamado.query.options(joinedload(Chamado.tecnico)).filter(
            Chamado.status_validacao == 'Pendente',
            Chamado.batch_id.isnot(None)
        ).order_by(Chamado.data_atendimento.desc(), Chamado.id).all()
        
        # Agrupar por batch_id
        batches_dict = defaultdict(list)
        for c in chamados:
            batches_dict[c.batch_id].append(c)
        
        # Converter para lista otimizada
        result = []
        for batch_id, chamados_list in batches_dict.items():
            if not chamados_list:
                continue
            
            primeiro = chamados_list[0]
            
            # Extrair cliente do tipo_resolucao (formato: "Desfecho (Cliente)")
            cliente = ''
            if primeiro.tipo_resolucao and '(' in primeiro.tipo_resolucao:
                cliente = primeiro.tipo_resolucao.split('(')[-1].rstrip(')')
            
            # Preparar lista de chamados para o modal
            chamados_detalhe = []
            codigos_jira = []
            valor_total = Decimal('0.00')
            horas_total = Decimal('0.00')
            
            for c in chamados_list:
                # User Request: Show Cost (Technician Payment) instead of Revenue
                # NOW DECIMAL
                valor_custo = Decimal(str(c.custo_atribuido or '0.00'))
                valor_total += valor_custo
                
                horas = Decimal(str(c.horas_trabalhadas or '0.00'))
                horas_total += horas
                
                if c.codigo_chamado:
                    codigos_jira.append(c.codigo_chamado)
                
                # Handle hora_inicio/hora_fim - can be time object or string
                hora_inicio_str = None
                hora_fim_str = None
                if c.hora_inicio:
                    hora_inicio_str = c.hora_inicio.strftime('%H:%M') if hasattr(c.hora_inicio, 'strftime') else str(c.hora_inicio)[:5]
                if c.hora_fim:
                    hora_fim_str = c.hora_fim.strftime('%H:%M') if hasattr(c.hora_fim, 'strftime') else str(c.hora_fim)[:5]
                
                chamados_detalhe.append({
                    'id': c.id,
                    'codigo': c.codigo_chamado or f'ID-{c.id}',
                    'tipo': c.tipo_servico or 'N/A',
                    'valor': float(valor_custo), # Frontend expects float usually
                    'horas': float(horas),
                    'hora_inicio': hora_inicio_str,
                    'hora_fim': hora_fim_str,
                    'peca': c.peca_usada or '-',
                    'obs': c.observacoes or '' 
                })
            
            result.append({
                'batch_id': batch_id,
                'tecnico_nome': primeiro.tecnico.nome if primeiro.tecnico else 'N/A',
                'tecnico_id': primeiro.tecnico_id,
                'data': primeiro.data_atendimento.strftime('%d/%m/%Y') if primeiro.data_atendimento else 'N/A',
                'data_raw': primeiro.data_atendimento,
                'cliente': cliente or 'Não identificado',
                'cidade': primeiro.cidade or 'N/A',
                'qnt_chamados': len(chamados_list),
                'valor_total': float(valor_total), # Frontend display
                'horas_total': float(horas_total),
                'chamados_lista': chamados_detalhe,
                'jira_codes': ','.join(codigos_jira),
                'chamados_ids': [c.id for c in chamados_list]
            })
        
        # Ordenar por data (mais recente primeiro)
        result.sort(key=lambda x: x['data_raw'] or '', reverse=True)
        return result

    @staticmethod
    def update(id, data, user_id=None):
        from decimal import Decimal
        chamado = ChamadoService.get_by_id(id)
        
        # Capture old state for audit
        old_data = {
            'status': chamado.status_chamado,
            'valor_receita': float(chamado.valor_receita_servico or 0),
            'loja': chamado.loja,
            'horas': float(chamado.horas_trabalhadas or 0),
            'custo': float(chamado.custo_atribuido or 0),
            'observacoes': chamado.observacoes
        }
        
        horario_inicio = data.get('horario_inicio')
        horario_saida = data.get('horario_saida')
        
        if 'tecnico_id' in data: chamado.tecnico_id = int(data['tecnico_id'])
        if 'codigo_chamado' in data: chamado.codigo_chamado = data.get('codigo_chamado', '')
        if 'loja' in data: chamado.loja = data.get('loja', '')
        if 'data_atendimento' in data: chamado.data_atendimento = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
        if horario_inicio: chamado.horario_inicio = datetime.strptime(horario_inicio, '%H:%M').time()
        if horario_saida: chamado.horario_saida = datetime.strptime(horario_saida, '%H:%M').time()
        if 'fsa_codes' in data: chamado.fsa_codes = data.get('fsa_codes', '')
        if 'tipo_servico' in data: chamado.tipo_servico = data['tipo_servico']
        from src.utils.domain import normalize_status
        if 'tipo_resolucao' in data: chamado.tipo_resolucao = data.get('tipo_resolucao', 'Resolvido')
        if 'status_chamado' in data: chamado.status_chamado = normalize_status(data.get('status_chamado', 'Pendente'))
        if 'endereco' in data: chamado.endereco = data.get('endereco', '')
        if 'observacoes' in data: chamado.observacoes = data.get('observacoes', '')
        
        def to_d(val): return Decimal(str(val or '0.00'))

        # Financeiro Updates
        if 'valor_receita_servico' in data:
            chamado.valor_receita_servico = to_d(data.get('valor_receita_servico'))
            
        if 'valor_receita_peca' in data:
            chamado.valor_receita_peca = to_d(data.get('valor_receita_peca'))
        
        # Update Related Fields if provided
        if 'peca_usada' in data: chamado.peca_usada = data.get('peca_usada')
        if 'custo_peca' in data: chamado.custo_peca = to_d(data.get('custo_peca'))
        if 'fornecedor_peca' in data: chamado.fornecedor_peca = data.get('fornecedor_peca')
        
        # FIX (2026-01): Allow manual override of hours and cost in Decimal
        if 'horas_trabalhadas' in data:
             chamado.horas_trabalhadas = to_d(data.get('horas_trabalhadas'))
        
        if 'custo_atribuido' in data:
             chamado.custo_atribuido = to_d(data.get('custo_atribuido'))

        chamado.valor_receita_total = (chamado.valor_receita_servico or Decimal(0)) + (chamado.valor_receita_peca or Decimal(0))
        chamado.valor = chamado.valor_receita_total
        
        # Calculate changes
        changes = {}
        new_data = {
            'status': chamado.status_chamado,
            'valor_receita': float(chamado.valor_receita_servico or 0),
            'loja': chamado.loja,
            'horas': float(chamado.horas_trabalhadas or 0),
            'custo': float(chamado.custo_atribuido or 0),
            'observacoes': chamado.observacoes
        }
        
        for k, v in new_data.items():
            if v != old_data.get(k):
                changes[k] = {'old': old_data.get(k), 'new': v}
        
        if changes:
            AuditService.log_change(
                model_name='Chamado',
                object_id=chamado.id,
                action='UPDATE',
                changes=changes,
                user_id=user_id
            )
        
        return chamado

    # Máquina de Estados - Transições Válidas
    VALID_STATUS_TRANSITIONS = {
        'Pendente': ['Em Andamento', 'Concluído', 'Cancelado'],
        'Em Andamento': ['Concluído', 'Cancelado', 'Pendente'],
        'Concluído': ['SPARE', 'Cancelado'],  # Não pode voltar para Pendente/Em Andamento
        'SPARE': ['Concluído', 'Cancelado'],
        'Cancelado': [],  # Estado final, não pode transicionar
    }
    
    @staticmethod
    def update_status(id, status):
        """
        Atualiza status do chamado com validação de transições.
        Caller deve gerenciar transação.
        """
        from src.utils.domain import normalize_status
        
        chamado = ChamadoService.get_by_id(id)
        old_status = chamado.status_chamado
        
        # Normalizar status de entrada
        status = normalize_status(status)
        
        # Validar transição
        valid_transitions = ChamadoService.VALID_STATUS_TRANSITIONS.get(old_status, [])
        
        if status not in valid_transitions and status != old_status:
            raise ValueError(
                f"Transição inválida: '{old_status}' → '{status}'. "
                f"Transições permitidas: {valid_transitions}"
            )
        
        # Se já está no mesmo status, não faz nada
        if status == old_status:
            return chamado
        
        # Impedir mudança de status se chamado já foi pago
        if chamado.pago or chamado.pagamento_id:
            raise ValueError(
                "Não é possível alterar status de chamado que já foi pago ou está em lote."
            )
        
        chamado.status_chamado = status
        
        # Audit log
        AuditService.log_change(
            model_name='Chamado',
            object_id=chamado.id,
            action='STATUS_CHANGE',
            changes=f"'{old_status}' → '{status}'"
        )
        
        # db.session.commit() # REMOVIDO
        return chamado

    @staticmethod
    def delete(id, user_id):
        """
        Exclui chamado com SOFT DELETE.
        
        REFATORADO (2026-01): Troca HARD DELETE por SOFT DELETE.
        Motivo: db.session.delete() quebra FK com stock_movements.chamado_id
        e destrói rastreabilidade de auditoria.
        
        O chamado permanece no banco com status_validacao='Excluído'.
        Caller deve gerenciar transação.
        """
        chamado = ChamadoService.get_by_id(id)
        
        # Security Check
        if chamado.pago or chamado.pagamento_id:
            raise ValueError("Não é possível excluir um chamado que já foi pago ou está em lote fechado.")
            
        AuditService.log_change(
            model_name='Chamado',
            object_id=chamado.id,
            action='SOFT_DELETE',
            changes=f"Soft-deleted Chamado {chamado.codigo_chamado or chamado.id}"
        )
        
        batch_id_to_recalc = chamado.batch_id

        # SOFT DELETE - marca como excluído em vez de deletar
        chamado.status_validacao = 'Excluído'
        chamado.motivo_rejeicao = 'Excluído pelo usuário'
        chamado.data_rejeicao = datetime.utcnow()
        chamado.rejeitado_por_id = user_id
        
        # Trigger Batch Recalculation if part of a batch
        if batch_id_to_recalc:
            # B2: Flush to ensure 'Excluído' status is visible to recalculation query
            db.session.flush()
            ChamadoService.recalculate_batch(batch_id_to_recalc)

        # db.session.commit() # REMOVIDO

    @staticmethod
    def recalculate_batch(batch_id):
        """
        Recalcula custos de todos os chamados ativos de um lote.
        Necessário quando um item do lote é excluído ou rejeitado.
        
        HARDENING P0 (2026-01):
        - B4: Row-level lock (with_for_update)
        - B1: Deterministic Primary Selection (Revenue DESC, ID ASC)
        """
        import logging
        logger = logging.getLogger(__name__)

        # 1. Buscar chamados ativos do lote com LOCK
        # B4: with_for_update evita race condition em recálculo concorrente
        try:
            chamados = Chamado.query.filter(
                Chamado.batch_id == batch_id,
                Chamado.status_validacao.notin_(['Excluído', 'Rejeitado'])
            ).with_for_update().all()
        except Exception as e:
            # Fallback for DBs that might not support locking in this context or timeout
            logger.warning(f"Could not acquire lock for batch {batch_id}: {e}")
            chamados = Chamado.query.filter(
                Chamado.batch_id == batch_id,
                Chamado.status_validacao.notin_(['Excluído', 'Rejeitado'])
            ).all()
        
        if not chamados:
            return

        # 2. Ordenar para priorizar quem será o "Principal"
        # B1: Deterministic Sort -> Maior Receita primeiro, Menor ID desempata
        # Tuple comparison: (100, -1) > (100, -2) => True (because -1 > -2)
        # Result: ID 1 comes before ID 2 if revenues are equal.
        from decimal import Decimal
        chamados.sort(key=lambda x: (x.valor_receita_total or Decimal('0.00'), -x.id), reverse=True)
        
        logger.info(f"[BATCH] Recalculating Batch {batch_id}. Items: {len(chamados)}. New Primary: {chamados[0].id}")
        
        # 3. Preparar inputs para o PricingService
        chamados_inputs = []
        for c in chamados:
            # Extrair configuração atualizada do serviço/técnico
            config = PricingService.extract_servico_config(c.catalogo_servico, c.tecnico)
            
            # Recalcular também as horas se necessário (Mantenha float para horas, OK)
            horas = float(c.horas_trabalhadas or 2.0)
            
            ci = ChamadoInput(
                id=c.id,
                data_atendimento=c.data_atendimento,
                cidade=c.cidade or c.loja or "INDEFINIDO",
                loja=c.loja,
                horas_trabalhadas=horas,
                servico_config=config,
                fornecedor_peca=c.fornecedor_peca,
                custo_peca=float(c.custo_peca or 0), # PricingService uses float internally currently - converting here
                _original=c
            )
            chamados_inputs.append(ci)
            
        # 4. Calcular
        resultados = PricingService.calcular_custos_lote(chamados_inputs)
        
        # 5. Aplicar atualizações
        for c in chamados:
            res = resultados.get(c.id)
            if res:
                # Atualizar campos financeiros calculados
                # PricingService returns floats, converting to Decimal for storage if needed or letting SQLA handle it
                # Logic: Models use Numeric(10,2). Assigning float/Decimal is fine, SQLA casts.
                # However, for consistency we trust SQLA's casting of float unless we refactor PricingService to use Decimal entirely.
                # Given strict instruction: "avoid float() for decision... ensure precision".
                # The 'results' from PricingService are float. We can't fix Services float usage right now without larger refactor.
                # BUT we fixed the SORTING above to use Decimal (x.valor_receita_total is Numeric).
                
                c.custo_atribuido = res.custo_total
                c.valor_receita_servico = res.receita_servico
                # Nota: valor_receita_peca mantém o original pois depende de ContratoItem que não recalculamos aqui
                # Mas recalculamos o total com base no novo serviço
                
                total_peca = c.valor_receita_peca or Decimal('0.00')
                total_servico = Decimal(str(res.receita_total)) # Convert float result to Decimal for safe addition
                
                c.valor_receita_total = total_servico + total_peca
                
                # Atualizar flags
                c.is_adicional = res.is_adicional
                # c.valor_horas_extras = res.custo_horas_extras # Se tiver campo no model
                
                # Legacy support
                c.valor = c.valor_receita_total



    @staticmethod
    def get_evolution_stats():
        from sqlalchemy import func
        from datetime import timedelta
        
        # Last 6 months
        today = datetime.now().date()
        six_months_ago = today - timedelta(days=180) # Approx
        
        # Truncate to first day of that month
        start_date = six_months_ago.replace(day=1)
        
        # Dialect-specific date formatting
        bind = db.session.get_bind()
        if 'sqlite' in bind.dialect.name:
            mes_col = func.strftime('%Y-%m', Chamado.data_atendimento)
        else:
            # PostgreSQL assumes data_atendimento is date/timestamp
            mes_col = func.to_char(Chamado.data_atendimento, 'YYYY-MM')
        
        results = db.session.query(
            mes_col.label('mes'),
            func.sum(Chamado.valor).label('total_valor'),
            func.count(Chamado.id).label('total_qtd')
        ).filter(
            Chamado.data_atendimento >= start_date,
            Chamado.status_chamado == 'Concluído'
        ).group_by(mes_col).order_by(mes_col).all()
        
        # Format for Chart.js
        labels = []
        custos = []
        volume = []
        
        # Map results to easy lookup
        data_map = {r.mes: r for r in results}
        
        # Generate last 6 months labels strictly
        # Note: This simple loop might miss months if no data, so we fill zeros
        current = start_date
        while current <= today:
            key = current.strftime('%Y-%m')
            label = current.strftime('%b/%Y') # e.g. Dec/2025
            
            val = data_map.get(key)
            labels.append(label)
            custos.append(float(val.total_valor) if val and val.total_valor else 0.0)
            volume.append(int(val.total_qtd) if val else 0)
            
            # Increment month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
                
        return {
            'labels': labels,
            'custos': custos,
            'volume': volume
        }

    @staticmethod
    def get_dashboard_stats():
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        chamados_mes = Chamado.query.filter(
            db.extract('month', Chamado.data_atendimento) == current_month,
            db.extract('year', Chamado.data_atendimento) == current_year
        ).count()
        
        # Query otimizada para contar status em uma única ida ao banco
        results = db.session.query(Chamado.status_chamado, func.count(Chamado.id))\
            .group_by(Chamado.status_chamado).all()
            
        # Inicializa com zero
        chamados_por_status = {
            'Pendente': 0,
            'Em Andamento': 0,
            'Concluído': 0,
            'Cancelado': 0
        }
        
        # Preenche com resultados reais
        for status, count in results:
            if status in chamados_por_status:
                chamados_por_status[status] = count
            else:
                # Caso haja algum status fora do padrão, adiciona ou ignora
                chamados_por_status[status] = count

        return {
            'chamados_mes': chamados_mes,
            'chamados_por_status': chamados_por_status,
            # Eager load tecnico in dashboard ultimos to prevent N+1 in dashboard
            'ultimos': Chamado.query.options(joinedload(Chamado.tecnico)).order_by(Chamado.data_criacao.desc()).limit(5).all()
        }
