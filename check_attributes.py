from src import create_app
from src.services.tecnico_service import TecnicoService
from src.models import Tecnico

app = create_app()

with app.app_context():
    print("Testing TecnicoService attributes...")
    # Fetch all active
    tecnicos = TecnicoService.get_all({'status': 'Ativo'}, page=None)
    
    if not tecnicos:
        print("No active tecnicos found to test. Skipping attribute check.")
    else:
        t = tecnicos[0]
        try:
             val = t.total_a_pagar
             print(f"SUCCESS: tecnico.total_a_pagar is accessible (Value: {val})")
        except AttributeError:
             print("FAILURE: tecnico.total_a_pagar raised AttributeError")
             
        try:
             val = t.total_atendimentos_nao_pagos
             print(f"SUCCESS: tecnico.total_atendimentos_nao_pagos is accessible (Value: {val})")
        except AttributeError:
             print("FAILURE: tecnico.total_atendimentos_nao_pagos raised AttributeError")
             
    # Test specific route logic simulation
    print("\nSimulating financeiro_routes logic:")
    try:
        tecnicos_com_pendente = [t for t in tecnicos if t.total_a_pagar > 0]
        print(f"SUCCESS: Filtering by total_a_pagar worked. Count: {len(tecnicos_com_pendente)}")
    except Exception as e:
        print(f"FAILURE: Filtering failed with {e}")

