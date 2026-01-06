
from app import create_app
from src.models import Chamado, Tecnico, db

app = create_app()

with app.app_context():
    # Identify the technician
    t = Tecnico.query.filter(Tecnico.saldo_atual > 0).first()
    if not t:
        print("No technician with valid balance found.")
        exit(1)
        
    print(f"Technician: {t.nome} (ID: {t.id})")
    print(f"Saldo Atual: {t.saldo_atual}")
    
    # Run the query exactly as in api_routes.py
    chamados = Chamado.query.filter(
        Chamado.tecnico_id == t.id,
        Chamado.status_chamado.in_(['Concluído', 'SPARE']),
        Chamado.status_validacao == 'Aprovado',
        Chamado.pago == False,
        Chamado.pagamento_id == None
    ).all()
    
    print(f"Found {len(chamados)} pending chamados.")
    
    for c in chamados:
        print(f" - ID: {c.id}, Status: {c.status_chamado}, Valid: {c.status_validacao}, Custo: {c.custo_atribuido}")

    # If 0 found, let's debug why.
    if len(chamados) == 0:
        print("DEBUG: Checking all chamados for this tech...")
        all_c = Chamado.query.filter_by(tecnico_id=t.id).all()
        for c in all_c:
             print(f" - ID: {c.id} | Status: {c.status_chamado} | Valid: {c.status_validacao} | Pago: {c.pago} | PID: {c.pagamento_id}")
