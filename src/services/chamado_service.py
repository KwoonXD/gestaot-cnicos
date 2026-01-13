
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
from .pricing_service import (
    HORAS_FRANQUIA_PADRAO,
    VALOR_HORA_EXTRA_DEFAULT,
    VALOR_ATENDIMENTO_BASE,
    VALOR_ADICIONAL_LOJA
)

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
        total_geral = 0.0
        
        for c in chamados:
            # Confia no valor calculado na criação (já considera Retorno=0 se regra aplicada)
            # Mas como segurança, se for nulo, usa 0
            valor_final = float(c.valor_receita_total or 0.0)
            
            nome_servico = c.catalogo_servico.nome if c.catalogo_servico else c.tipo_servico
            
            itens.append({
                'data': c.data_atendimento.strftime('%d/%m/%Y'),
                'codigo': c.codigo_chamado or f"ID-{c.id}",
                'cidade': c.cidade,
                'estado': c.tecnico.estado if c.tecnico else 'PB', # Default PB is fallback
                'servico': nome_servico,
                'valor': valor_final
            })
            total_geral += valor_final
            
        return {
            'itens': itens,
            'total_geral': total_geral,
            'periodo': f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
        }

    @staticmethod
    def create_multiplo(logistica, fsas):
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

            # Valores calculados pelo PricingService
            valor_receita_servico = resultado['valor_receita_servico']
            valor_receita_total = resultado['valor_receita_total']
            custo_atribuido = resultado['custo_atribuido']
            horas_trabalhadas = resultado['horas_trabalhadas']
            is_adicional = resultado['is_adicional']

            # Inicializa valores de peça
            peca_nome = ""
            custo_peca = 0.0
            valor_receita_peca = 0.0
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
                    # PricingService.get_valor_peca faz fallback automatico para preco padrao
                    valor_receita_peca = PricingService.get_valor_peca(cliente_id, item.id) if cliente_id else (item.valor_receita or 0.0)

                    # Se Fornecedor = Tecnico -> Custo informado manualmente
                    if fornecedor == 'Tecnico':
                        custo_peca = float(fsa.get('custo_peca', 0))

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

        db.session.commit()
        return criados

    @staticmethod
    def aprovar_chamados(ids_lista, user_id):
        """Aprova chamados para processamento financeiro"""
        try:
            count = 0
            for chamado_id in ids_lista:
                chamado = Chamado.query.get(chamado_id)
                if chamado and chamado.status_validacao == 'Pendente':
                    chamado.status_validacao = 'Aprovado'
                    chamado.data_validacao = datetime.utcnow()
                    chamado.validado_por_id = user_id
                    
                    # Automating Ledger Credit
                    from .financeiro_service import FinanceiroService
                    FinanceiroService.registrar_credito_servico(chamado)
                    
                    count += 1
            db.session.commit()
            
            AuditService.log_change(
                model_name='Chamado',
                object_id=str(ids_lista),
                action='APPROVE_BATCH',
                changes=f"Approved {count} chamados"
            )
            return count
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def rejeitar_chamados(ids_lista, user_id, motivo):
        """
        Rejeita chamados com HARD DELETE e notifica o criador.
        """
        from src.models import Notification
        
        try:
            deleted_count = 0
            notified_users = []
            deleted_codes = []
            
            for chamado_id in ids_lista:
                chamado = Chamado.query.get(chamado_id)
                if not chamado:
                    continue
                
                # Capturar dados antes de deletar
                codigo = chamado.codigo_chamado or f"ID-{chamado.id}"
                data_atend = chamado.data_atendimento.strftime('%d/%m/%Y') if chamado.data_atendimento else 'N/A'
                tecnico_nome = chamado.tecnico.nome if chamado.tecnico else 'N/A'
                cidade = chamado.cidade or 'N/A'
                created_by = chamado.created_by_id
                
                # Criar notificação se houver criador
                if created_by:
                    notif = Notification(
                        user_id=created_by,
                        title=f"⚠️ Chamado {codigo} Rejeitado",
                        message=f"O chamado foi rejeitado por um supervisor.\n\n"
                                f"📋 Código: {codigo}\n"
                                f"📅 Data: {data_atend}\n"
                                f"👤 Técnico: {tecnico_nome}\n"
                                f"📍 Local: {cidade}\n\n"
                                f"❌ Motivo: {motivo}",
                        notification_type='danger'
                    )
                    db.session.add(notif)
                    notified_users.append(created_by)
                
                # HARD DELETE
                db.session.delete(chamado)
                deleted_count += 1
                deleted_codes.append(codigo)
            
            db.session.commit()
            
            # Audit log
            AuditService.log_change(
                model_name='Chamado',
                object_id=str(deleted_codes),
                action='REJECT_DELETE',
                changes=f"Hard-deleted {deleted_count} chamados. Motivo: {motivo[:100]}"
            )
            
            return deleted_count
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_pendentes_validacao():
        """Retorna chamados pendentes de validação"""
        return Chamado.query.options(joinedload(Chamado.tecnico)).filter(
            Chamado.status_validacao == 'Pendente'
        ).order_by(Chamado.data_atendimento.desc()).all()

    @staticmethod
    def get_grouped_by_batch(filters=None):
        """
        Retorna chamados agrupados por batch_id (lote de atendimento).
        Útil para visualização e geração de links JQL.
        """
        from collections import defaultdict
        
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
                    'total_receita': sum(float(c.valor_receita_total or 0) for c in chamados_list),
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
            valor_total = 0.0
            
            for c in chamados_list:
                # User Request: Show Cost (Technician Payment) instead of Revenue
                valor_custo = float(c.custo_atribuido or 0)
                valor_total += valor_custo
                
                if c.codigo_chamado:
                    codigos_jira.append(c.codigo_chamado)
                
                chamados_detalhe.append({
                    'id': c.id,
                    'codigo': c.codigo_chamado or f'ID-{c.id}',
                    'tipo': c.tipo_servico or 'N/A',
                    'valor': valor_custo, # Agora reflete o custo técnico
                    'peca': c.peca_usada or '-'
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
                'valor_total': valor_total,
                'chamados_lista': chamados_detalhe,
                'jira_codes': ','.join(codigos_jira),
                'chamados_ids': [c.id for c in chamados_list]
            })
        
        # Ordenar por data (mais recente primeiro)
        result.sort(key=lambda x: x['data_raw'] or '', reverse=True)
        return result

    @staticmethod
    def aprovar_batch(batch_id, user_id):
        """Aprova todos os chamados de um lote"""
        try:
            chamados = Chamado.query.filter_by(
                batch_id=batch_id,
                status_validacao='Pendente'
            ).all()
            
            count = 0
            for c in chamados:
                c.status_validacao = 'Aprovado'
                c.data_validacao = datetime.utcnow()
                c.validado_por_id = user_id
                
                # Automating Ledger Credit
                from .financeiro_service import FinanceiroService
                FinanceiroService.registrar_credito_servico(c)
                
                count += 1
            
            db.session.commit()
            
            AuditService.log_change(
                model_name='Chamado',
                object_id=batch_id,
                action='APPROVE_BATCH',
                changes=f"Approved {count} chamados in batch"
            )
            return count
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def rejeitar_batch(batch_id, user_id, motivo):
        """Rejeita e deleta todos os chamados de um lote, notificando criadores"""
        from src.models import Notification
        
        try:
            chamados = Chamado.query.filter_by(
                batch_id=batch_id,
                status_validacao='Pendente'
            ).all()
            
            deleted_count = 0
            deleted_codes = []
            
            for chamado in chamados:
                # Capturar dados antes de deletar
                codigo = chamado.codigo_chamado or f"ID-{chamado.id}"
                data_atend = chamado.data_atendimento.strftime('%d/%m/%Y') if chamado.data_atendimento else 'N/A'
                tecnico_nome = chamado.tecnico.nome if chamado.tecnico else 'N/A'
                cidade = chamado.cidade or 'N/A'
                created_by = chamado.created_by_id
                
                # Criar notificação se houver criador
                if created_by:
                    notif = Notification(
                        user_id=created_by,
                        title=f"⚠️ Chamado {codigo} Rejeitado",
                        message=f"O chamado foi rejeitado por um supervisor.\n\n"
                                f"📋 Código: {codigo}\n"
                                f"📅 Data: {data_atend}\n"
                                f"👤 Técnico: {tecnico_nome}\n"
                                f"📍 Local: {cidade}\n\n"
                                f"❌ Motivo: {motivo}",
                        notification_type='danger'
                    )
                    db.session.add(notif)
                
                # HARD DELETE
                db.session.delete(chamado)
                deleted_count += 1
                deleted_codes.append(codigo)
            
            db.session.commit()
            
            AuditService.log_change(
                model_name='Chamado',
                object_id=batch_id,
                action='REJECT_BATCH_DELETE',
                changes=f"Hard-deleted {deleted_count} chamados. Motivo: {motivo[:100]}"
            )
            
            return deleted_count
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_by_id(id):
        return Chamado.query.get_or_404(id)

    @staticmethod
    def create(data):
        # Legacy/Single Create Wrapper adapting to new model
        # Just create a single item list and call create_multiplo
        fsa_data = {
            'codigo_chamado': data.get('codigo_chamado'),
            'tipo_resolucao': data.get('tipo_resolucao'),
            'peca_usada': data.get('peca_usada'),
            'fornecedor_peca': data.get('fornecedor_peca'),
            'custo_peca': data.get('custo_peca')
        }
        logistica = {
            'tecnico_id': data.get('tecnico_id'),
            'data_atendimento': data.get('data_atendimento'),
            'cidade': data.get('cidade') or data.get('loja') or 'Indefinido' # Fallback
        }
        return ChamadoService.create_multiplo(logistica, [fsa_data])[0]

    @staticmethod
    def update(id, data):
        try:
            chamado = ChamadoService.get_by_id(id)
            
            # Capture old state for audit
            old_data = {
                'status': chamado.status_chamado,
                'valor_receita': float(chamado.valor_receita_servico or 0),
                'loja': chamado.loja
            }
            
            horario_inicio = data.get('horario_inicio')
            horario_saida = data.get('horario_saida')
            
            chamado.tecnico_id = int(data['tecnico_id'])
            chamado.codigo_chamado = data.get('codigo_chamado', '')
            chamado.loja = data.get('loja', '')
            chamado.data_atendimento = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
            chamado.horario_inicio = datetime.strptime(horario_inicio, '%H:%M').time() if horario_inicio else None
            chamado.horario_saida = datetime.strptime(horario_saida, '%H:%M').time() if horario_saida else None
            chamado.fsa_codes = data.get('fsa_codes', '')
            chamado.tipo_servico = data['tipo_servico']
            chamado.tipo_resolucao = data.get('tipo_resolucao', 'Resolvido')
            chamado.status_chamado = data.get('status_chamado', 'Pendente')
            chamado.endereco = data.get('endereco', '')
            chamado.observacoes = data.get('observacoes', '')
            
            # Financeiro Updates - Preserve existing values if not in payload
            if 'valor_receita_servico' in data:
                rec_servico = float(data.get('valor_receita_servico') or 0.0)
                chamado.valor_receita_servico = rec_servico
            else:
                rec_servico = float(chamado.valor_receita_servico or 0.0)
                
            if 'valor_receita_peca' in data:
                rec_peca = float(data.get('valor_receita_peca') or 0.0)
                chamado.valor_receita_peca = rec_peca
            else:
                rec_peca = float(chamado.valor_receita_peca or 0.0)
            
            # Update Related Fields if provided
            if 'peca_usada' in data: chamado.peca_usada = data.get('peca_usada')
            if 'custo_peca' in data: chamado.custo_peca = float(data.get('custo_peca') or 0.0)
            if 'fornecedor_peca' in data: chamado.fornecedor_peca = data.get('fornecedor_peca')
            
            chamado.valor_receita_total = rec_servico + rec_peca
            chamado.valor = chamado.valor_receita_total
            
            # Calculate changes
            changes = {}
            new_data = {
            'status': chamado.status_chamado,
            'valor_receita': float(chamado.valor_receita_servico),
            'loja': chamado.loja
            }
            
            for k, v in new_data.items():
                if v != old_data[k]:
                    changes[k] = {'old': old_data[k], 'new': v}
            
            if changes:
                AuditService.log_change(
                    model_name='Chamado',
                    object_id=chamado.id,
                    action='UPDATE',
                    changes=changes
                )
            
            db.session.commit()
            return chamado
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update_status(id, status):
        try:
            chamado = ChamadoService.get_by_id(id)
            chamado.status_chamado = status
            db.session.commit()
            return chamado
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def delete(id, user_id):
        try:
            chamado = ChamadoService.get_by_id(id)
            
            # Security Check
            if chamado.pago or chamado.pagamento_id:
                raise ValueError("Não é possível excluir um chamado que já foi pago ou está em lote fechado.")
                
            AuditService.log_change(
                model_name='Chamado',
                object_id=chamado.id,
                action='DELETE',
                changes=f"Deleted Chamado {chamado.codigo_chamado or chamado.id}"
            )
            
            db.session.delete(chamado)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_evolution_stats():
        from sqlalchemy import func
        from datetime import timedelta
        
        # Last 6 months
        today = datetime.now().date()
        six_months_ago = today - timedelta(days=180) # Approx
        
        # Truncate to first day of that month
        start_date = six_months_ago.replace(day=1)
        
        results = db.session.query(
            func.strftime('%Y-%m', Chamado.data_atendimento).label('mes'),
            func.sum(Chamado.valor).label('total_valor'),
            func.count(Chamado.id).label('total_qtd')
        ).filter(
            Chamado.data_atendimento >= start_date,
            Chamado.status_chamado == 'Concluído'
        ).group_by('mes').order_by('mes').all()
        
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
