from ..models import db, Tecnico, ItemLPU, TecnicoStock, StockMovement, User
from datetime import datetime

class StockService:
    
    @staticmethod
    def transferir_para_tecnico(item_id, tecnico_id, quantidade, user_id=None, observacao=None):
        """
        Transfere peças do Estoque Central (Origem=None) para um Técnico (Destino=Tecnico).
        Cria movimentação e atualiza saldo.
        """
        try:
            # Validations
            if quantidade <= 0:
                raise ValueError("Quantidade deve ser positiva.")
                
            tecnico = Tecnico.query.get(tecnico_id)
            item = ItemLPU.query.get(item_id)
            
            if not tecnico or not item:
                raise ValueError("Técnico ou Item não encontrado.")
                
            # Create Movement
            movement = StockMovement(
                item_lpu_id=item_id,
                origem_tecnico_id=None, # Central Stock
                destino_tecnico_id=tecnico_id,
                quantidade=quantidade,
                tipo_movimento='ENVIO',
                created_by_id=user_id,
                observacao=observacao
            )
            db.session.add(movement)
            
            # Update/Create Stock Record
            stock_record = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
            if stock_record:
                stock_record.quantidade += quantidade
            else:
                stock_record = TecnicoStock(
                    tecnico_id=tecnico_id,
                    item_lpu_id=item_id,
                    quantidade=quantidade
                )
                db.session.add(stock_record)
                
            db.session.commit()
            return movement
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def consumir_peca(tecnico_id, item_id, quantidade=1, chamado_id=None, user_id=None):
        """
        Registra consumo de peça pelo técnico (Uso em Chamado).
        Decrements stock. Raises error if insufficient stock.
        """
        try:
            stock_record = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
            
            if not stock_record or stock_record.quantidade < quantidade:
                # Opcional: Permitir saldo negativo? O user disse "validar se tem saldo, senão erro".
                raise ValueError(f"Estoque insuficiente. Disponível: {stock_record.quantidade if stock_record else 0}")
            
            stock_record.quantidade -= quantidade
            
            # Create Movement (Uso)
            # Destino is None (Consumed), or we can track it differently?
            # Model says: "Uso: Origem=Tecnico -> Destino=Chamado (ou NULL)"
            # Destino_tecnico_id is FK to Tecnico. We can't put ChamadoID there.
            # Usually Destination=None means consumed/left the system (or back to central).
            # For usage, Destination=None is fine, Type='USO'.
            
            movement = StockMovement(
                item_lpu_id=item_id,
                origem_tecnico_id=tecnico_id,
                destino_tecnico_id=None, 
                quantidade=quantidade,
                tipo_movimento='USO',
                created_by_id=user_id,
                observacao=f"Uso no Chamado ID {chamado_id}" if chamado_id else "Consumo avulso"
            )
            db.session.add(movement)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_stock_by_tecnico(tecnico_id):
        return TecnicoStock.query.filter_by(tecnico_id=tecnico_id).all()

    @staticmethod
    def devolver_para_central(tecnico_id, item_id, quantidade, user_id=None):
        """
        Devolução de peça do técnico para a central.
        """
        try:
            stock_record = TecnicoStock.query.filter_by(tecnico_id=tecnico_id, item_lpu_id=item_id).first()
             
            if not stock_record or stock_record.quantidade < quantidade:
                raise ValueError(f"Estoque insuficiente para devolução. Disponível: {stock_record.quantidade if stock_record else 0}")
                
            stock_record.quantidade -= quantidade
            
            movement = StockMovement(
                item_lpu_id=item_id,
                origem_tecnico_id=tecnico_id,
                destino_tecnico_id=None, # Central is destination, but how to distinguish from usage?
                # Actually usage is Type='USO'. Return is Type='DEVOLUCAO'.
                # Conventions: Dest=None + Type='DEVOLUCAO' = Central.
                quantidade=quantidade,
                tipo_movimento='DEVOLUCAO',
                created_by_id=user_id,
                observacao="Devolução ao estoque central"
            )
            
            db.session.add(movement)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e
