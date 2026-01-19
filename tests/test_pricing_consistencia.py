import pytest
from datetime import date
from src.models import Chamado, Tecnico, CatalogoServico, Cliente
from src.services.pricing_service import PricingService, VALOR_ATENDIMENTO_BASE, VALOR_ADICIONAL_LOJA

def test_pricing_consistency(app, db):
    """
    Test P0: Verify that 'Real Time' pricing matches 'Batch' pricing 
    by ensuring the refactored logic correctly identifies batch peers.
    """
    # 1. Setup Data
    cliente = Cliente(nome="Cliente Teste Pricing")
    db.session.add(cliente)
    db.session.flush()

    tecnico = Tecnico(
        nome="Tecnico Pricing", 
        valor_por_atendimento=VALOR_ATENDIMENTO_BASE, 
        valor_adicional_loja=VALOR_ADICIONAL_LOJA,
        contato="00", cidade="Natal", estado="RN", data_inicio=date(2025,1,1)
    )
    db.session.add(tecnico)
    
    # Servicos
    s_normal = CatalogoServico(
        nome="Servico Normal", 
        cliente_id=cliente.id,
        valor_custo_tecnico=VALOR_ATENDIMENTO_BASE,
        valor_adicional_custo=VALOR_ADICIONAL_LOJA,
        paga_tecnico=True,
        pagamento_integral=False
    )
    s_integral = CatalogoServico(
        nome="Servico Integral", 
        cliente_id=cliente.id,
        valor_custo_tecnico=VALOR_ATENDIMENTO_BASE,
        paga_tecnico=True,
        pagamento_integral=True # Does not consume slot
    )
    db.session.add(s_normal)
    db.session.add(s_integral)
    db.session.commit()

    print(f"Base: {VALOR_ATENDIMENTO_BASE}, Adicional: {VALOR_ADICIONAL_LOJA}")

    # --- SCENARIO 1: Normal + Normal (Same Day/City) ---
    # Call 1: Persisted, 1st of batch
    c1 = Chamado(
        tecnico_id=tecnico.id, catalogo_servico_id=s_normal.id,
        data_atendimento=date(2025,5,1), cidade="Natal",
        status_chamado='Concluído', status_validacao='Aprovado'
    )
    db.session.add(c1)
    db.session.commit()
    
    # Call 2: Being approved (Transient validation)
    # Note: Logic relies on finding "other approved calls" in DB.
    c2 = Chamado(
        tecnico_id=tecnico.id, catalogo_servico_id=s_normal.id,
        data_atendimento=date(2025,5,1), cidade="Natal",
        status_chamado='Concluído', status_validacao='Aprovado'
    )
    
    # Calculate
    custo_c2 = PricingService.calcular_custo_tempo_real(c2, tecnico)
    
    # Assert: Should be ADICIONAL because C1 occupies the slot
    assert abs(custo_c2 - VALOR_ADICIONAL_LOJA) < 0.01, \
        f"C2 should be Additional ({VALOR_ADICIONAL_LOJA}), got {custo_c2}"

    # --- SCENARIO 2: Integral + Normal (Same Day/City) ---
    # Call 3: Integral/SPARE (Persisted)
    c3 = Chamado(
        tecnico_id=tecnico.id, catalogo_servico_id=s_integral.id,
        data_atendimento=date(2025,6,1), cidade="Natal",
        status_chamado='Concluído', status_validacao='Aprovado'
    )
    db.session.add(c3)
    db.session.commit()
    
    # Call 4: Normal (Being approved)
    c4 = Chamado(
        tecnico_id=tecnico.id, catalogo_servico_id=s_normal.id,
        data_atendimento=date(2025,6,1), cidade="Natal",
        status_chamado='Concluído', status_validacao='Aprovado'
    )
    
    # Calculate
    custo_c4 = PricingService.calcular_custo_tempo_real(c4, tecnico)
    
    # Assert: Should be FULL BASE because C3 (Integral) does NOT consume slot
    assert abs(custo_c4 - VALOR_ATENDIMENTO_BASE) < 0.01, \
        f"C4 should be Full Base ({VALOR_ATENDIMENTO_BASE}), got {custo_c4}"
