from ..models import db, Tecnico, ItemLPU, TecnicoStock, StockMovement, User
from datetime import datetime

class StockService:
    @staticmethod
    def get_saldo(tecnico_id, item_id):
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        return stock.quantidade if stock else 0

    @staticmethod
    def _update_stock(tecnico_id, item_id, delta, user_id, tipo, obs=None):
        stock = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
        if not stock:
            stock = TecnicoStock(tecnico_id=tecnico_id, item_lpu_id=item_id, quantidade=0)
            db.session.add(stock)
        
        stock.quantidade += delta
        
        # Log Movimento
        mov = StockMovement(
            item_lpu_id=item_id,
            tipo_movimento=tipo,
            quantidade=abs(delta),
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
    def transferir_sede_para_tecnico(tecnico_id, item_id, qtd, user_id, obs=None):
        """Sede envia para técnico (Aumenta saldo do técnico)"""
        return StockService._update_stock(tecnico_id, item_id, qtd, user_id, 'ENVIO', obs)

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
