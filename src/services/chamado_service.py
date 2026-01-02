from ..models import db, Chamado, Tecnico, CatalogoServico, ItemLPU, Cliente
from datetime import datetime
from .audit_service import AuditService
import uuid
import re
from sqlalchemy.orm import joinedload
from sqlalchemy import or_

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
        Retorna float (ex: 2.5 para 2h30m).
        Tratamento: Se fim < início, assume virada de dia (+24h).
        """
        if not hora_inicio or not hora_fim:
            return 2.0  # Default
        
        try:
            from datetime import timedelta
            
            # Parse strings
            inicio = datetime.strptime(hora_inicio.strip(), '%H:%M')
            fim = datetime.strptime(hora_fim.strip(), '%H:%M')
            
            # Calcula diferença
            diff = fim - inicio
            
            # Se negativo, assumir virada de dia
            if diff.total_seconds() < 0:
                diff = diff + timedelta(hours=24)
            
            # Converte para horas decimais
            horas = diff.total_seconds() / 3600
            return round(horas, 2)
        except Exception as e:
            print(f"Erro ao calcular horas: {e}")
            return 2.0  # Default em caso de erro

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
    def create_multiplo(dados_logistica, lista_fsas):
        """
        Cria múltiplos chamados com cálculo de RECEITA (por FSA) e CUSTO (Lote).
        
        Regras de Custo (Técnico):
        - Index 0 (Principal): Recebe Base + Horas Extras.
        - Index > 0 (Adicional): Recebe valor adicional fixo.
        - Horas Extras: (Total Horas - 2) * Valor Hora Adicional.
        """
        from datetime import datetime as dt
        from flask_login import current_user
        
        try:
            tecnico_id = int(dados_logistica['tecnico_id'])
            
            # Buscar Técnico para pegar valores de contrato
            tecnico = Tecnico.query.get(tecnico_id)
            if not tecnico:
                raise ValueError(f"Técnico ID {tecnico_id} não encontrado.")
                
            cidade = dados_logistica.get('cidade', 'Indefinido')
            cliente_nome = dados_logistica.get('cliente_nome', '')
            data_str = dados_logistica['data_atendimento']
            data_atend = dt.strptime(data_str, '%Y-%m-%d').date()
            
            # Gerar UUID único para este lote
            batch_id = str(uuid.uuid4())
            
            # Capturar criador
            created_by = getattr(current_user, 'id', None) if current_user and current_user.is_authenticated else None
            
            # --- 1. Calcular Horas Totais do Lote ---
            # Assume-se que o horário é compartilhado ou pega do primeiro
            # O front-end geralmente manda o horário em todos, ou no cabeçalho.
            # Vamos pegar do primeiro item da lista para referência do lote.
            primeiro_fsa = lista_fsas[0] if lista_fsas else {}
            hora_inicio_str = primeiro_fsa.get('hora_inicio', '')
            hora_fim_str = primeiro_fsa.get('hora_fim', '')
            
            horas_reais = ChamadoService.calculate_hours_worked(hora_inicio_str, hora_fim_str)
            horas_franquia = 2.0
            
            # Cálculo HE
            horas_extras = max(0.0, horas_reais - horas_franquia)
            valor_hora_adicional = float(tecnico.valor_hora_adicional or 30.0) # Default R$ 30 se nulo
            valor_pagar_he = horas_extras * valor_hora_adicional
            
            created_chamados = []
            
            for index, fsa in enumerate(lista_fsas):
                chamado = Chamado()
                is_principal = (index == 0)
                
                # --- Cabeçalho ---
                chamado.tecnico_id = tecnico.id
                chamado.cidade = cidade
                chamado.data_atendimento = data_atend
                chamado.status_chamado = 'Concluído'
                chamado.batch_id = batch_id
                chamado.status_validacao = 'Pendente'
                chamado.created_by_id = created_by
                
                # --- Item / FSA ---
                raw_code = fsa.get('codigo_chamado', '')
                chamado.codigo_chamado = ChamadoService.extract_fsa_code(raw_code)
                chamado.is_adicional = not is_principal
                
                # --- Horários ---
                chamado.hora_inicio = hora_inicio_str
                chamado.hora_fim = hora_fim_str
                chamado.horas_trabalhadas = horas_reais
                
                # --- RECEITA (Valor que a empresa ganha) ---
                # Busca Serviço no Banco
                catalogo_id = fsa.get('catalogo_servico_id')
                catalogo = CatalogoServico.query.get(catalogo_id) if catalogo_id else None
                
                servico_nome = catalogo.nome if catalogo else 'Serviço Avulso'
                
                # --- Lógica de Retorno/SPARE (Smart Billing) ---
                rec_servico = float(catalogo.valor_receita) if catalogo else 0.0
                
                is_retorno = False
                if servico_nome:
                    nome_lower = servico_nome.lower()
                    if 'retorno' in nome_lower or 'spare' in nome_lower:
                        is_retorno = True
                
                # Default peca vars
                rec_peca = 0.0
                peca_nome = fsa.get('peca_usada', '') or ''
                # fornecedor_peca is retrieved later but needed for logic
                fornecedor_peca_input = fsa.get('fornecedor_peca', 'Empresa') 
                
                if is_retorno:
                    # Se for retorno, SÓ cobra se a peça for do Cliente
                    if fornecedor_peca_input == 'Cliente':
                         # Cobra valor cheio (mantém rec_servico)
                         pass
                    else:
                         # Isenção de cobrança
                         rec_servico = 0.0
                
                chamado.catalogo_servico_id = catalogo.id if catalogo else None
                chamado.tipo_servico = servico_nome
                chamado.tipo_resolucao = f"{servico_nome} ({cliente_nome})" if cliente_nome else servico_nome
                
                # Busca Peça no Banco ou Fallback
                rec_peca = 0.0
                peca_nome = fsa.get('peca_usada', '') or ''
                peca_id = fsa.get('peca_id')
                
                if peca_id:
                    item_lpu = ItemLPU.query.get(peca_id)
                    if item_lpu:
                        peca_nome = item_lpu.nome
                        rec_peca = float(item_lpu.valor_receita or 0)
                elif peca_nome.strip():
                    # Fallback por nome
                    item_lpu = ItemLPU.query.filter(ItemLPU.nome.ilike(f"%{peca_nome.strip()}%")).first()
                    if item_lpu:
                         rec_peca = float(item_lpu.valor_receita or 0)
                         peca_nome = item_lpu.nome

                chamado.valor_receita_servico = rec_servico
                chamado.valor_receita_peca = rec_peca
                chamado.valor_receita_total = rec_servico + rec_peca
                chamado.peca_usada = peca_nome.strip() if peca_nome.strip() else None
                chamado.valor = chamado.valor_receita_total # Compatibilidade legado
                
                # --- CUSTO (Quanto paga ao técnico) ---
                custo_atribuido = 0.0
                
                if is_principal:
                    # Principal: Base + HE
                    base = float(tecnico.valor_por_atendimento or 120.0)
                    custo_atribuido = base + valor_pagar_he
                    chamado.valor_horas_extras = valor_pagar_he # Registra quanto foi HE
                else:
                    # Adicional: Valor fixo extra (loja ou ativo)
                    custo_atribuido = float(tecnico.valor_adicional_loja or 20.0)
                    chamado.valor_horas_extras = 0.0
                
                chamado.custo_atribuido = custo_atribuido
                
                # Custo Peça (Se comprada pelo técnico)
                chamado.fornecedor_peca = fsa.get('fornecedor_peca', 'Empresa')
                chamado.custo_peca = float(fsa.get('custo_peca', 0.0)) if chamado.fornecedor_peca == 'Tecnico' else 0.0
                
                # --- STOCK VALIDATION HOOK ---
                # Se a peça é da Empresa, assume-se que saiu do estoque do técnico (Almoxarifado Virtual)
                # A menos que seja um item que não controla estoque (ex: cabos menores? Para MVP, todos Itens LPU controlam).
                if chamado.fornecedor_peca == 'Empresa' and 'item_lpu' in locals() and item_lpu:
                     from .stock_service import StockService
                     # Consome 1 unidade. Se falhar, faz raise e rollback em tudo.
                     # Passamos None no chamado_id pois ainda não tem ID. Opcional: Atualizar obs depois?
                     # Ou apenas logar "Uso no Batch {batch_id}"
                     try:
                        StockService.consumir_peca(
                            tecnico_id=tecnico.id, 
                            item_id=item_lpu.id, 
                            quantidade=1, 
                            user_id=created_by,
                            chamado_id=None # Será vinculado via Batch/Data
                        )
                     except ValueError as ve:
                        # Repassa erro de estoque amigavel
                        raise ValueError(f"Estoque Insuficiente para o item '{item_lpu.nome}': {str(ve)}")

                db.session.add(chamado)
                created_chamados.append(chamado)
                
            db.session.commit()
            
            msg_audit = f"Batch {batch_id}: {len(created_chamados)} FSAs. Tech: {tecnico.nome}. Total Time: {horas_reais}h. HE: R$ {valor_pagar_he:.2f}"
            AuditService.log_change(
                model_name='Chamado',
                object_id=batch_id,
                action='CREATE_MULTI_V2',
                changes=msg_audit
            )
                
            return created_chamados
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro critical em create_multiplo: {e}")
            raise e

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
                valor = float(c.valor_receita_total or 0)
                valor_total += valor
                
                if c.codigo_chamado:
                    codigos_jira.append(c.codigo_chamado)
                
                chamados_detalhe.append({
                    'id': c.id,
                    'codigo': c.codigo_chamado or f'ID-{c.id}',
                    'tipo': c.tipo_servico or 'N/A',
                    'valor': valor,
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
            
            # Financeiro Updates 
            rec_servico = float(data.get('valor_receita_servico', 0.0))
            rec_peca = float(data.get('valor_receita_peca', 0.0))
            
            chamado.valor_receita_servico = rec_servico
            chamado.peca_usada = data.get('peca_usada')
            chamado.valor_receita_peca = rec_peca
            chamado.custo_peca = float(data.get('custo_peca', 0.0))
            chamado.fornecedor_peca = data.get('fornecedor_peca', 'Empresa')
            
            chamado.valor = rec_servico + rec_peca
            
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
        
        chamados_por_status = {}
        for status in ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']:
             chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
             
        return {
            'chamados_mes': chamados_mes,
            'chamados_por_status': chamados_por_status,
            # Eager load tecnico in dashboard ultimos to prevent N+1 in dashboard
            'ultimos': Chamado.query.options(joinedload(Chamado.tecnico)).order_by(Chamado.data_criacao.desc()).limit(5).all()
        }
