from ..models import db, Chamado, Tecnico
from datetime import datetime
from .audit_service import AuditService
import uuid
import re

class ChamadoService:
    LPU_LIST = {
        # Reparo / Itens básicos
        'Scanner': 180.0,
        'CPU gerencia': 250.0,
        'Monitor': 200.0,
        'Teclado pdv': 250.0,
        'Impressora Fiscal': 280.0,
        'Memoria ram': 300.0,
        'SSD/HD': 300.0,
        'Cabo Scanner Zebra': 180.0,
        'Cabo USB p/ Impressora 2mt': 38.70,
        'HDMI': 43.86,
        'VGA': 47.30,
        'Cabo de força tripolar': 38.70,
        'Cabo de força bipolar': 30.96,
        'Cabo de força p/ fonte ATX': 38.70,
        'Cabo de força SATA': 43.77,
        'Cabo SATA': 27.43,
        'Patch cord 3mt': 35.24,
        'Conector RJ 45': 2.06,
        'Conector RJ11': 2.06,
        'Fonte CPU Interna mini': 300.00,
        'Fonte Externa': 180.00,
        
        # Revenda / Peças Novas
        'Scanner BR520 (Novo)': 289.00,
        'CPU gerencia (Novo)': 1000.00,
        'CPU PDV (Novo)': 1350.00,
        'Monitor (Novo)': 500.00,
        'Teclado GERTEC 44 (Novo)': 700.90,
        'Impressora Fiscal MP4200 HS (Novo)': 515.00,
        'Placa mãe (Novo)': 600.00,
        'Gaveta GD56 M (Novo)': 289.00,
        'Cabeça impressão (Novo)': 2300.00
    }

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
            from datetime import datetime, timedelta
            
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
        query = Chamado.query.join(Tecnico)
        
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
                from sqlalchemy import or_
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
    def create_multiplo(dados_logistica, lista_fsas):
        """
        Cria múltiplos chamados usando CatalogoServico unificado.
        - Usa catalogo_servico_id com regras de negócio (exige_peca, paga_tecnico)
        - Registra horas_trabalhadas para cálculo de horas extras
        - Gera batch_id para agrupar FSAs
        - Sanitiza códigos FSA (extrai de URLs do Jira)
        """
        import datetime
        from datetime import datetime as dt
        from src.models import CatalogoServico, ItemLPU
        from flask_login import current_user
        
        tecnico_id = int(dados_logistica['tecnico_id'])
        cidade = dados_logistica.get('cidade', 'Indefinido')
        cliente_nome = dados_logistica.get('cliente_nome', '')
        data_str = dados_logistica['data_atendimento']
        data_atend = dt.strptime(data_str, '%Y-%m-%d').date()
        
        # Gerar UUID único para este lote de atendimento
        batch_id = str(uuid.uuid4())
        
        # Capturar o usuário criador se disponível
        created_by = None
        try:
            if current_user and current_user.is_authenticated:
                created_by = current_user.id
        except:
            pass
        
        created_chamados = []
        
        for index, fsa in enumerate(lista_fsas):
            chamado = Chamado()
            
            # --- Dados Cabeçalho ---
            chamado.tecnico_id = tecnico_id
            chamado.cidade = cidade
            chamado.data_atendimento = data_atend
            chamado.status_chamado = 'Finalizado'
            chamado.batch_id = batch_id
            chamado.status_validacao = 'Pendente'
            chamado.created_by_id = created_by
            
            # --- Dados Item (FSA) - COM SANITIZAÇÃO ---
            raw_code = fsa.get('codigo_chamado', '')
            chamado.codigo_chamado = ChamadoService.extract_fsa_code(raw_code)
            
            # --- CatalogoServico (Novo modelo unificado) ---
            catalogo_id = fsa.get('catalogo_servico_id')
            catalogo = None
            servico_nome = ''
            servico_valor = 0.0
            
            if catalogo_id:
                catalogo = CatalogoServico.query.get(catalogo_id)
                if catalogo:
                    servico_nome = catalogo.nome
                    servico_valor = float(catalogo.valor_receita or 0)
                    chamado.catalogo_servico_id = catalogo.id
            
            chamado.tipo_servico = servico_nome
            chamado.tipo_resolucao = f"{servico_nome} ({cliente_nome})" if cliente_nome else servico_nome
            chamado.is_adicional = (index > 0)
            
            # --- Horas Trabalhadas (calculado de hora_inicio/hora_fim) ---
            hora_inicio = fsa.get('hora_inicio', '')
            hora_fim = fsa.get('hora_fim', '')
            chamado.hora_inicio = hora_inicio
            chamado.hora_fim = hora_fim
            chamado.horas_trabalhadas = ChamadoService.calculate_hours_worked(hora_inicio, hora_fim)
            
            # --- Regras de RECEITA (Faturamento para WT) ---
            # Se o catálogo não paga técnico (ex: Improdutivo), receita é 0
            # Mas a empresa ainda fatura o valor do catálogo
            rec_servico = servico_valor
            
            # Receita Peça
            rec_peca = 0.0
            peca_id = fsa.get('peca_id')
            peca_nome = fsa.get('peca_usada', '')
            peca_valor = float(fsa.get('peca_valor', 0))
            
            if peca_id:
                item_lpu = ItemLPU.query.get(peca_id)
                if item_lpu:
                    peca_nome = item_lpu.nome
                    peca_valor = float(item_lpu.valor_receita or 0)
            elif peca_nome and peca_nome.strip():
                # Fallback para lista hardcoded se não tiver ID
                for nome, valor in ChamadoService.LPU_LIST.items():
                    if nome.lower() in peca_nome.lower():
                        peca_valor = valor
                        break
            
            rec_peca = peca_valor if peca_nome and peca_nome.strip() else 0.0
            
            chamado.valor_receita_servico = rec_servico
            chamado.valor_receita_peca = rec_peca
            chamado.valor_receita_total = rec_servico + rec_peca
            chamado.peca_usada = peca_nome.strip() if peca_nome and peca_nome.strip() else None
            
            # --- Dados de Peça/Custo ---
            chamado.fornecedor_peca = fsa.get('fornecedor_peca', 'Empresa')
            if chamado.fornecedor_peca == 'Tecnico':
                chamado.custo_peca = float(fsa.get('custo_peca', 0.0))
            else:
                chamado.custo_peca = 0.0
                
            chamado.valor = chamado.valor_receita_total
            
            db.session.add(chamado)
            created_chamados.append(chamado)
            
        db.session.commit()
        
        AuditService.log_change(
            model_name='Chamado',
            object_id=batch_id,
            action='CREATE_MULTI',
            changes=f"Created {len(created_chamados)} FSAs for Tech {tecnico_id} in {cidade}"
        )
            
        return created_chamados

    @staticmethod
    def aprovar_chamados(ids_lista, user_id):
        """Aprova chamados para processamento financeiro"""
        from datetime import datetime
        count = 0
        for chamado_id in ids_lista:
            chamado = Chamado.query.get(chamado_id)
            if chamado and chamado.status_validacao == 'Pendente':
                chamado.status_validacao = 'Aprovado'
                chamado.data_validacao = datetime.utcnow()
                chamado.validado_por_id = user_id
                count += 1
        db.session.commit()
        
        AuditService.log_change(
            model_name='Chamado',
            object_id=str(ids_lista),
            action='APPROVE_BATCH',
            changes=f"Approved {count} chamados"
        )
        return count

    @staticmethod
    def rejeitar_chamados(ids_lista, user_id, motivo):
        """
        Rejeita chamados com HARD DELETE e notifica o criador.
        - Captura dados para notificação
        - Cria Notification para o criador
        - DELETA permanentemente o chamado
        """
        from datetime import datetime
        from src.models import Notification
        
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

    @staticmethod
    def get_pendentes_validacao():
        """Retorna chamados pendentes de validação"""
        return Chamado.query.filter(
            Chamado.status_validacao == 'Pendente'
        ).order_by(Chamado.data_atendimento.desc()).all()

    @staticmethod
    def get_grouped_by_batch(filters=None):
        """
        Retorna chamados agrupados por batch_id (lote de atendimento).
        Útil para visualização e geração de links JQL.
        """
        from collections import defaultdict
        
        query = Chamado.query.filter(Chamado.batch_id.isnot(None))
        
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
        chamados = Chamado.query.filter(
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
        from datetime import datetime
        
        chamados = Chamado.query.filter_by(
            batch_id=batch_id,
            status_validacao='Pendente'
        ).all()
        
        count = 0
        for c in chamados:
            c.status_validacao = 'Aprovado'
            c.data_validacao = datetime.utcnow()
            c.validado_por_id = user_id
            count += 1
        
        db.session.commit()
        
        AuditService.log_change(
            model_name='Chamado',
            object_id=batch_id,
            action='APPROVE_BATCH',
            changes=f"Approved {count} chamados in batch"
        )
        return count

    @staticmethod
    def rejeitar_batch(batch_id, user_id, motivo):
        """Rejeita e deleta todos os chamados de um lote, notificando criadores"""
        from datetime import datetime
        from src.models import Notification
        
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
        rec_servico, rec_peca = ChamadoService._calcular_receita(data)
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

    @staticmethod
    def update_status(id, status):
        chamado = ChamadoService.get_by_id(id)
        chamado.status_chamado = status
        db.session.commit()
        return chamado

    @staticmethod
    def delete(id, user_id):
        chamado = ChamadoService.get_by_id(id)
        
        # Security Check
        if chamado.pago or chamado.pagamento_id:
            raise ValueError("Não é possível excluir um chamado que já foi pago ou está em lote fechado.")
            
        # Log before delete (since object will be gone)
        # However, for delete usually we log the ID and maybe a snapshot. 
        # AuditService.log_change(action='DELETE')
        AuditService.log_change(
            model_name='Chamado',
            object_id=chamado.id,
            action='DELETE',
            changes=f"Deleted Chamado {chamado.codigo_chamado or chamado.id}"
        )
        
        db.session.delete(chamado)
        db.session.commit()

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
        # Avoid direct import of constant to prevent circular dep, or pass it in. 
        # Assuming we can just query distinct or use list.
        # We'll use the query grouping for efficiency in real app, but for now simple:
        for status in ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']:
             chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
             
        return {
            'chamados_mes': chamados_mes,
            'chamados_por_status': chamados_por_status,
            'ultimos': Chamado.query.order_by(Chamado.data_criacao.desc()).limit(5).all()
        }
