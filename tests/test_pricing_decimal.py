
import pytest
from decimal import Decimal
from src.services.pricing_service import PricingService, ChamadoInput, ServicoConfig

def test_decimal_precision_constants():
    """Verify that all constants are Decimals."""
    from src.services.pricing_service import (
        HORAS_FRANQUIA_PADRAO,
        VALOR_ATENDIMENTO_BASE
    )
    assert isinstance(HORAS_FRANQUIA_PADRAO, Decimal)
    assert isinstance(VALOR_ATENDIMENTO_BASE, Decimal)

def test_calculate_hours_worked():
    """Verify hour calculation returns Decimal."""
    # 2 hours 30 mins
    res = PricingService.calculate_hours_worked('09:00', '11:30')
    assert isinstance(res, Decimal)
    assert res == Decimal('2.50')

    # Overnight (23:00 to 01:00) -> 2 hours
    res = PricingService.calculate_hours_worked('23:00', '01:00')
    assert isinstance(res, Decimal)
    assert res == Decimal('2.00')

def test_pricing_calculation_flow():
    """Verify end-to-end pricing calculation uses Decimal."""
    config = ServicoConfig(
        valor_custo_tecnico=Decimal('100.00'),
        valor_hora_adicional_custo=Decimal('50.00'),
        horas_franquia=Decimal('2.00')
    )
    
    # Input: 3.5 hours worked (1.5h extra)
    # Expected: 100.00 + (1.5 * 50.00) = 100.00 + 75.00 = 175.00
    chamado_input = ChamadoInput(
        id=1,
        horas_trabalhadas=Decimal('3.50'),
        servico_config=config
    )
    
    res = PricingService.calcular_custo_unitario(chamado_input, is_primeiro_lote=True)
    
    assert isinstance(res.custo_total, Decimal)
    assert isinstance(res.custo_servico, Decimal)
    assert isinstance(res.custo_horas_extras, Decimal)
    
    assert res.custo_servico == Decimal('100.00')
    assert res.custo_horas_extras == Decimal('75.00')
    assert res.custo_total == Decimal('175.00')

def test_float_drift_prevention():
    """
    Simulate a scenario where float would fail or drift, 
    ensuring Decimal handles it correctly.
    (Simple example: 0.1 + 0.2 != 0.3 in float)
    """
    # Force values that often cause float issues
    val1 = Decimal('0.10')
    val2 = Decimal('0.20')
    sum_val = val1 + val2
    assert sum_val == Decimal('0.30')
    
    # Pricing context
    # 1.1 hours extra * 30.00
    # Float: 1.1 * 30.0 = 33.0 (usually ok, but let's test types)
    
    config = ServicoConfig(
        valor_custo_tecnico=Decimal('0.00'),
        valor_hora_adicional_custo=Decimal('0.10'), # 10 cents per hour
        horas_franquia=Decimal('0.00')
    )
    
    # 3 hours work -> 0.30 cost
    chamado_input = ChamadoInput(
        horas_trabalhadas=Decimal('3.00'),
        servico_config=config
    )
    res = PricingService.calcular_custo_unitario(chamado_input)
    assert res.custo_total == Decimal('0.30')
