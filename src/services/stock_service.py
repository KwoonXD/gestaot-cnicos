from ..models import db, Tecnico, ItemLPU, TecnicoStock, StockMovement, User, Notification
from datetime import datetime
from sqlalchemy import func

class StockService:
    @staticmethod
    def get_saldo(tecnico_id, item_id):
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        return stock.quantidade if stock else 0

    @staticmethod
    def _update_stock(tecnico_id, item_id, delta, user_id, tipo, obs=None, custo_unitario=None):
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        if not stock:
            stock = TecnicoStock(tecnico_id=tecnico_id, item_lpu_id=item_id, quantidade=0)
            db.session.add(stock)

        stock.quantidade += delta

        # Log Movimento (com custo para auditoria)
        mov = StockMovement(
            item_lpu_id=item_id,
            tipo_movimento=tipo,
            quantidade=abs(delta),
            custo_unitario=custo_unitario,
            observacao=obs,
            created_by_id=user_id
        )

        if delta > 0: # Entrada no técnico (ENVIO ou AJUSTE positivo)
            mov.destino_tecnico_id = tecnico_id
        else: # Saída do técnico (DEVOLUCAO ou AJUSTE negativo)
            mov.origem_tecnico_id = tecnico_id

        db.session.add(mov)
        db.session.commit()
        return stock

    @staticmethod
    def transferir_sede_para_tecnico(tecnico_id, item_id, qtd, user_id, obs=None, custo_aquisicao=None):
        """
        Sede envia para técnico (Aumenta saldo do técnico).

        Se custo_aquisicao for informado, recalcula o Custo Médio Ponderado:
        Novo Custo = ((Qtd Atual * Custo Atual) + (Qtd Entrada * Custo Entrada)) / (Qtd Atual + Qtd Entrada)
        """
        # Calcular custo médio ponderado se custo informado
        if custo_aquisicao is not None and custo_aquisicao > 0:
            item = ItemLPU.query.get(item_id)
            if item:
                # Buscar quantidade total atual em todos os técnicos
                qtd_atual_total = db.session.query(func.sum(TecnicoStock.quantidade)).filter(
                    TecnicoStock.item_lpu_id == item_id,
                    TecnicoStock.quantidade > 0
                ).scalar() or 0

                custo_atual = float(item.valor_custo or 0)

                # Cálculo de Custo Médio Ponderado
                valor_total_atual = qtd_atual_total * custo_atual
                valor_total_entrada = qtd * custo_aquisicao
                nova_quantidade = qtd_atual_total + qtd

                if nova_quantidade > 0:
                    novo_custo_medio = (valor_total_atual + valor_total_entrada) / nova_quantidade
                    item.valor_custo = round(novo_custo_medio, 2)

        return StockService._update_stock(tecnico_id, item_id, qtd, user_id, 'ENVIO', obs, custo_aquisicao)

    @staticmethod
    def devolver_tecnico_para_sede(tecnico_id, item_id, qtd, user_id, obs=None):
        """Técnico devolve para sede (Diminui saldo do técnico)"""
        return StockService._update_stock(tecnico_id, item_id, -qtd, user_id, 'DEVOLUCAO', obs)

    @staticmethod
    def ajustar_saldo(tecnico_id, item_id, nova_qtd, user_id, obs=None):
        """Define o saldo exato (Para inventário/correção)"""
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        atual = stock.quantidade if stock else 0
        delta = nova_qtd - atual
        
        if delta != 0:
            return StockService._update_stock(tecnico_id, item_id, delta, user_id, 'AJUSTE', obs)

    @staticmethod
    def get_stock_by_tecnico(tecnico_id):
        return TecnicoStock.query.filter_by(tecnico_id=tecnico_id).all()

    # ==========================================================================
    # INTEGRACAO COM CHAMADOS (Pilar de Custos de Materiais)
    # ==========================================================================

    @staticmethod
    def registrar_uso_chamado(tecnico_id, item_id, chamado_id, user_id, quantidade=1):
        """
        Registra uso de peça em chamado com rastreabilidade completa.

        Fluxo:
        1. Valida existência do item
        2. Verifica saldo do técnico
        3. Decrementa TecnicoStock
        4. Cria StockMovement vinculado ao chamado
        5. Retorna custo da peça para preenchimento do chamado

        Args:
            tecnico_id: ID do técnico que usou a peça
            item_id: ID do ItemLPU utilizado
            chamado_id: ID do chamado onde a peça foi usada
            user_id: ID do usuário que registrou (auditoria)
            quantidade: Quantidade utilizada (default: 1)

        Returns:
            float: Custo total da peça (valor_custo * quantidade)

        Raises:
            ValueError: Se item não existe ou saldo insuficiente
        """
        # 1. Buscar item
        item = ItemLPU.query.get(item_id)
        if not item:
            raise ValueError(f"Item com ID {item_id} não encontrado no catálogo.")

        # 2. Verificar saldo
        stock = TecnicoStock.query.filter_by(
            tecnico_id=tecnico_id,
            item_lpu_id=item_id
        ).first()

        saldo_atual = stock.quantidade if stock else 0

        if saldo_atual < quantidade:
            raise ValueError(
                f"Saldo insuficiente de '{item.nome}'. "
                f"Disponível: {saldo_atual}, Solicitado: {quantidade}"
            )

        # 3. Decrementar estoque
        stock.quantidade -= quantidade

        # 4. Criar movimentação vinculada ao chamado
        mov = StockMovement(
            item_lpu_id=item_id,
            origem_tecnico_id=tecnico_id,
            chamado_id=chamado_id,
            quantidade=quantidade,
            tipo_movimento='USO',
            observacao=f"Uso em chamado #{chamado_id}",
            created_by_id=user_id
        )
        db.session.add(mov)

        # 5. Calcular custo
        custo_unitario = float(item.valor_custo or 0.0)
        custo_total = custo_unitario * quantidade

        # 6. Verificar se estoque ficou baixo e criar alerta se necessário
        StockService.verificar_estoque_baixo(tecnico_id, item_id)

        # Não faz commit aqui - deixa para o chamado_service gerenciar a transação
        return custo_total

    @staticmethod
    def get_custo_item(item_id):
        """Retorna o custo de um item (para cálculos externos)."""
        item = ItemLPU.query.get(item_id)
        return float(item.valor_custo or 0.0) if item else 0.0

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
                'valor_custo': float(alerta.item_lpu.valor_custo or 0) if alerta.item_lpu else 0
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
            'valor_imobilizado': float(valor_total),
            'alertas_estoque_baixo': alertas
        }
