from ..models import db, Tecnico, ItemLPU, TecnicoStock, StockMovement, User, Notification
from datetime import datetime
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_UP

# Helper para formatar valores monetarios como string
def _format_money(value):
    """Converte valor para string com 2 casas decimais."""
    if value is None:
        return '0.00'
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return str(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

class StockService:
    @staticmethod
    def get_saldo(tecnico_id, item_id):
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        return stock.quantidade if stock else 0

    @staticmethod
    def _update_stock(tecnico_id, item_id, delta, user_id, tipo, obs=None, custo_unitario=None, chamado_id=None):
        """
        Atualiza estoque do técnico e registra movimento.
        
        REFATORADO (2026-01): 
        1. Row locking para evitar race condition (saldo negativo).
        2. Retry on creation para evitar IntegrityError (creation race).
        3. Suporte a chamado_id para rastreabilidade unificada.
        
        Args:
            tecnico_id: ID do técnico
            item_id: ID do ItemLPU
            delta: Quantidade (positivo = entrada, negativo = saída)
            user_id: ID do usuário que está fazendo a operação
            tipo: Tipo de movimento (ENVIO, DEVOLUCAO, USO, AJUSTE)
            obs: Observação opcional
            custo_unitario: Custo unitário para auditoria
            chamado_id: ID do chamado vinculado (opcional)
            
        Returns:
            TecnicoStock atualizado
            
        Raises:
            ValueError: Se saldo resultante for negativo
        """
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                # 1. Tentar buscar com LOCK
                stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).with_for_update().first()
                
                if not stock:
                    # Se não existe, cria (insert)
                    # Pode falhar com IntegrityError se outra thread criar neste exato momento
                    try:
                        # Criar savepoint para isolar falha do INSERT
                        db.session.begin_nested() 
                        stock = TecnicoStock(tecnico_id=tecnico_id, item_lpu_id=item_id, quantidade=0)
                        db.session.add(stock)
                        db.session.flush() # Força INSERT
                        # Se passou aqui, insert ok. COMMIT do savepoint ocorre automaticamente no exit do begin_nested (sucesso)
                    except Exception:
                        # Se falhou (duplicate key), rollback do savepoint e retry loop
                        db.session.rollback() # Rollback do savepoint
                        if attempt < MAX_RETRIES - 1:
                            continue # Tenta de novo (agora deve achar no SELECT)
                        raise # Se excedeu retries, explode
                        
                # 2. Calcular novo saldo
                novo_saldo = stock.quantidade + delta
                
                # 3. Validação: Não permitir saldo negativo
                if novo_saldo < 0:
                    item = ItemLPU.query.get(item_id)
                    item_nome = item.nome if item else f"ID-{item_id}"
                    raise ValueError(
                        f"Saldo insuficiente: {item_nome} ficaria com {novo_saldo}. "
                        f"Saldo atual: {stock.quantidade}, Solicitado: {abs(delta)}"
                    )
                
                stock.quantidade = novo_saldo

                # 4. Log Movimento
                mov = StockMovement(
                    item_lpu_id=item_id,
                    tipo_movimento=tipo,
                    quantidade=abs(delta),
                    custo_unitario=custo_unitario,
                    observacao=obs,
                    created_by_id=user_id,
                    chamado_id=chamado_id # Novo campo suportado
                )

                if delta > 0: # Entrada (ENVIO, DEVOLUCAO SEDE->TEC, AJUSTE POSITIVO)
                    mov.destino_tecnico_id = tecnico_id
                else: # Saída (USO, DEVOLUCAO TEC->SEDE, AJUSTE NEGATIVO)
                    mov.origem_tecnico_id = tecnico_id

                db.session.add(mov)
                
                # Check alertas apenas se baixou estoque
                if delta < 0:
                    StockService.verificar_estoque_baixo(tecnico_id, item_id)
                
                db.session.flush() # Garante IDs
                return stock
                
            except Exception as e:
                # Se for o ValueError de saldo, propaga imediatamente
                if isinstance(e, ValueError):
                    raise e
                # Outros erros (DB), se estamos no loop de retry e não for a ultima tentativa...
                # Mas para update normal, não deveríamos ter erro de concorrência com row-lock,
                # exceto Deadlock. Vamos apenas propagar se não for o caso específico de criação.
                raise e

    @staticmethod
    def transferir_sede_para_tecnico(tecnico_id, item_id, qtd, user_id, obs=None, custo_aquisicao=None):
        """
        Sede envia para técnico (Aumenta saldo do técnico).
        """
        try:
            # Calcular custo médio ponderado se custo informado
            if custo_aquisicao is not None and custo_aquisicao > 0:
                item = ItemLPU.query.get(item_id)
                if item:
                    # Travar ItemLPU para update seguro do custo médio?
                    # Por enquanto, assumindo baixo risco de colisão em atualização de mestre de itens.
                    qtd_atual_total = db.session.query(func.sum(TecnicoStock.quantidade)).filter(
                        TecnicoStock.item_lpu_id == item_id,
                        TecnicoStock.quantidade > 0
                    ).scalar() or 0

                    custo_atual = Decimal(str(item.valor_custo or 0))

                    valor_total_atual = Decimal(str(qtd_atual_total)) * custo_atual
                    valor_total_entrada = Decimal(str(qtd)) * Decimal(str(custo_aquisicao))
                    nova_quantidade = qtd_atual_total + qtd

                    if nova_quantidade > 0:
                        novo_custo_medio = (valor_total_atual + valor_total_entrada) / Decimal(str(nova_quantidade))
                        item.valor_custo = novo_custo_medio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            result = StockService._update_stock(
                tecnico_id, item_id, qtd, user_id, 'ENVIO', obs, custo_aquisicao
            )
            return result
        except Exception as e:
            raise e

    @staticmethod
    def devolver_tecnico_para_sede(tecnico_id, item_id, qtd, user_id, obs=None):
        """Técnico devolve para sede (Diminui saldo do técnico)"""
        try:
            result = StockService._update_stock(
                tecnico_id, item_id, -qtd, user_id, 'DEVOLUCAO', obs
            )
            return result
        except Exception as e:
            raise e

    @staticmethod
    def ajustar_saldo(tecnico_id, item_id, nova_qtd, user_id, obs=None):
        """Define o saldo exato (Para inventário/correção)"""
        try:
            # Precisa buscar saldo atual sob lock para calcular delta correto
            # O _update_stock faz lock, mas aqui precisamos saber o delta ANTES.
            # Risco: Se saldo mudar entre leitura e update_stock.
            # Solução: Implementar AJUSTE ABSOLUTO no _update_stock?
            # Por simplicidade/prazo:
            # Vamos usar uma transação pequena aqui.
            
            stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).with_for_update().first()
            atual = stock.quantidade if stock else 0
            delta = nova_qtd - atual
            
            if delta != 0:
                # Passamos delta. Como já travamos a linha, o _update_stock vai travar de novo?
                # Sim, Reentrant lock no Postgres? Não, with_for_update na mesma txn é ok.
                # MAS, _update_stock faz nova query.
                # Melhor confiar no _update_stock e aceitar um pequeno race no cálculo do delta (ajuste é raro).
                # OU: Passa o delta calculado.
                
                result = StockService._update_stock(
                    tecnico_id, item_id, delta, user_id, 'AJUSTE', obs
                )
                return result
            return stock
        except Exception as e:
            raise e

    @staticmethod
    def get_stock_by_tecnico(tecnico_id):
        return TecnicoStock.query.filter_by(tecnico_id=tecnico_id).all()

    # ==========================================================================
    # INTEGRACAO COM CHAMADOS (Pilar de Custos de Materiais)
    # ==========================================================================

    @staticmethod
    def registrar_uso_chamado(tecnico_id, item_id, chamado_id, user_id, quantidade=1):
        """
        Registra uso de peça em chamado com rastreabilidade completa e LOCK.
        
        REFATORADO (2026-01): Delega para _update_stock para garantir atomicidade
        e prevenir race condition de saldo negativo.
        """
        # 1. Obter custo unitário para registro correto (auditoria)
        item = ItemLPU.query.get(item_id)
        if not item:
            raise ValueError(f"Item com ID {item_id} não encontrado.")
        
        custo_unitario = Decimal(str(item.valor_custo or 0))
        
        # 2. Executar baixa via método centralizado (com Lock e Rastreio)
        StockService._update_stock(
            tecnico_id=tecnico_id,
            item_id=item_id,
            delta=-quantidade, # Saída
            user_id=user_id,
            tipo='USO',
            obs=f"Uso em chamado #{chamado_id}",
            custo_unitario=custo_unitario, # Passa Decimal
            chamado_id=chamado_id
        )

        # 3. Retorna custo total para o ChamadoService usar
        custo_total = custo_unitario * Decimal(str(quantidade))
        return custo_total

    @staticmethod
    def get_custo_item(item_id):
        """Retorna o custo de um item como Decimal."""
        item = ItemLPU.query.get(item_id)
        return Decimal(str(item.valor_custo or 0)) if item else Decimal('0')

    @staticmethod
    def get_movimentacoes_chamado(chamado_id):
        """Retorna todas as movimentações de estoque vinculadas a um chamado."""
        return StockMovement.query.filter_by(chamado_id=chamado_id).all()

    # ==========================================================================
    # ALERTAS DE ESTOQUE
    # ==========================================================================

    @staticmethod
    def verificar_estoque_baixo(tecnico_id, item_id, limite=2):
        """
        Verifica se o estoque está baixo e cria notificação se necessário.

        Args:
            tecnico_id: ID do técnico
            item_id: ID do item
            limite: Quantidade mínima antes de alertar (default: 2)

        Returns:
            bool: True se estoque está baixo
        """
        stock = TecnicoStock.query.filter_by(
            tecnico_id=tecnico_id,
            item_lpu_id=item_id
        ).first()

        if stock and stock.quantidade <= limite:
            item = ItemLPU.query.get(item_id)
            tecnico = Tecnico.query.get(tecnico_id)

            if item and tecnico:
                # Notifica admins (user_id=1 por padrão, ajustar conforme necessário)
                admin_ids = db.session.query(User.id).filter(User.role == 'Admin').all()

                for (admin_id,) in admin_ids:
                    # Evita duplicatas (verifica se já existe notificação recente)
                    existe = Notification.query.filter(
                        Notification.user_id == admin_id,
                        Notification.title.contains(f'{tecnico.nome}'),
                        Notification.title.contains(f'{item.nome}'),
                        Notification.is_read == False
                    ).first()

                    if not existe:
                        notif = Notification(
                            user_id=admin_id,
                            title=f"Estoque Baixo: {item.nome}",
                            message=f"O técnico {tecnico.nome} possui apenas {stock.quantidade} "
                                    f"unidade(s) de '{item.nome}' em estoque.\n\n"
                                    f"Considere enviar reposição.",
                            notification_type='warning'
                        )
                        db.session.add(notif)

                return True

        return False

    @staticmethod
    def get_alertas_estoque_baixo(limite=2):
        """
        Retorna lista de técnicos com estoque baixo.

        Returns:
            List[dict]: Lista com alertas de estoque baixo
        """
        alertas = TecnicoStock.query.filter(
            TecnicoStock.quantidade <= limite,
            TecnicoStock.quantidade > 0
        ).all()

        resultado = []
        for alerta in alertas:
            resultado.append({
                'tecnico_id': alerta.tecnico_id,
                'tecnico_nome': alerta.tecnico.nome if alerta.tecnico else 'N/A',
                'item_id': alerta.item_lpu_id,
                'item_nome': alerta.item_lpu.nome if alerta.item_lpu else 'N/A',
                'quantidade': alerta.quantidade,
                'valor_custo': _format_money(alerta.item_lpu.valor_custo) if alerta.item_lpu else '0.00'
            })

        return resultado

    @staticmethod
    def get_resumo_estoque():
        """
        Retorna resumo geral do estoque.

        Returns:
            dict: Estatísticas do estoque
        """
        # Total de peças em rua
        total_pecas = db.session.query(
            func.sum(TecnicoStock.quantidade)
        ).filter(TecnicoStock.quantidade > 0).scalar() or 0

        # Valor total imobilizado
        valor_total = db.session.query(
            func.sum(TecnicoStock.quantidade * ItemLPU.valor_custo)
        ).join(ItemLPU, TecnicoStock.item_lpu_id == ItemLPU.id).filter(
            TecnicoStock.quantidade > 0
        ).scalar() or 0

        # Quantidade de alertas
        alertas = TecnicoStock.query.filter(
            TecnicoStock.quantidade <= 2,
            TecnicoStock.quantidade > 0
        ).count()

        return {
            'total_pecas': int(total_pecas),
            'valor_imobilizado': _format_money(valor_total),
            'alertas_estoque_baixo': alertas
        }
