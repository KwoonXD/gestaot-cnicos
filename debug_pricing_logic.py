from datetime import date
from unittest.mock import MagicMock
from src import create_app
from src.services.pricing_service import PricingService, ComputoCalculado, ChamadoInput, ServicoConfig
from src.models import Chamado, Tecnico, CatalogoServico

app = create_app()

def run_scenario():
    with app.app_context():
        # Setup context
        tecnico = Tecnico(id=1, valor_por_atendimento=100.0, valor_adicional_loja=50.0)
        
        # Servico A: Normal (Paga Tecnico=True, Integral=False)
        servico_normal = CatalogoServico(
            id=1, nome="Normal", 
            valor_custo_tecnico=100.0, 
            valor_adicional_custo=50.0,
            paga_tecnico=True, 
            pagamento_integral=False
        )
        
        # Servico B: Integral (Paga Tecnico=True, Integral=True)
        servico_integral = CatalogoServico(
            id=2, nome="Integral", 
            valor_custo_tecnico=100.0, 
            valor_adicional_custo=50.0,
            paga_tecnico=True, 
            pagamento_integral=True
        )

        print("\n--- SCENARIO 1: Two Normal Calls (Same Batch) ---")
        # 1st Call (already in DB)
        c1 = Chamado(
            id=101, tecnico_id=1, data_atendimento=date(2025,1,1), cidade="SP",
            catalogo_servico=servico_normal, status_chamado='Concluído', status_validacao='Aprovado'
        )
        # 2nd Call (Being approved now)
        c2 = Chamado(
            id=102, tecnico_id=1, data_atendimento=date(2025,1,1), cidade="SP",
            catalogo_servico=servico_normal, status_chamado='Concluído', status_validacao='Aprovado'
        )
        
        # Simulate DB for tempo_real (mocking the query)
        # In current logic, c2 is approved, sees c1 in DB.
        # Function: calcular_custo_tempo_real(c2, tecnico)
        # We need to mock the DB query inside PricingService.
        
        print("Skipping direct execution due to DB dependency. Proceeding to fix based on static analysis.")
        print("The plan is to enforce consistency by calling 'calcular_custos_lote' inside 'calcular_custo_tempo_real'.")

if __name__ == "__main__":
    run_scenario()
