try:
    from src.models import db, Tecnico, Lancamento, StockMovement
    print("Models imported successfully.")
except Exception as e:
    import traceback
    traceback.print_exc()
