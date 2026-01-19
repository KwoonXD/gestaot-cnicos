def test_import_services():
    """
    Test P0: Verify that critical services can be imported.
    This catches syntax errors, circular imports, and missing dependencies.
    """
    try:
        from src.services.chamado_service import ChamadoService
        assert ChamadoService is not None
    except ImportError as e:
        assert False, f"Failed to import ChamadoService: {e}"
    except SyntaxError as e:
        assert False, f"Syntax Error in ChamadoService: {e}"

    try:
        from src.services.financeiro_service import FinanceiroService
        assert FinanceiroService is not None
    except ImportError as e:
        assert False, f"Failed to import FinanceiroService: {e}"
        
    try:
        from src.services.pricing_service import PricingService
        assert PricingService is not None
    except ImportError as e:
        assert False, f"Failed to import PricingService: {e}"
