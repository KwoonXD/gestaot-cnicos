
import logging
import sys
from datetime import date
from decimal import Decimal

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from src import create_app, db
from src.utils.domain import normalize_city, normalize_status
from src.services.pricing_service import PricingService, ChamadoInput
from src.services.chamado_service import ChamadoService

def verify_domain():
    logger.info("=== VERIFICANDO DOMAIN CONSISTENCY ===")
    
    # Teste 1: normalize_city
    logger.info("--- Test 1: City Normalization ---")
    cities = [
        ("sao paulo", "SAO PAULO"),
        ("  SAO PAULO  ", "SAO PAULO"),
        ("São Paulo", "SAO PAULO"), # Se unicode remover acentos
        ("Belo   Horizonte", "BELO HORIZONTE"),
        (None, "INDEFINIDO")
    ]
    
    for input_val, expected in cities:
        result = normalize_city(input_val)
        logger.info(f"Input: '{input_val}' -> Result: '{result}' (Expected: '{expected}')")
        assert result == expected, f"Falha na normalização: {input_val} -> {result}"
        
    # Teste 2: Pricing Logic (Lote Key)
    logger.info("--- Test 2: Pricing Lote Key ---")
    d1 = date(2025, 1, 1)
    
    c1 = ChamadoInput(data_atendimento=d1, cidade="São Paulo")
    c2 = ChamadoInput(data_atendimento=d1, cidade="sao paulo ")
    
    key1 = PricingService.get_lote_key(c1)
    key2 = PricingService.get_lote_key(c2)
    
    logger.info(f"Key 1: {key1}")
    logger.info(f"Key 2: {key2}")
    
    assert key1 == key2, "Chaves de lote devem ser idênticas para mesma cidade (case insenstive)"
    
    # Teste 3: Status Normalization
    logger.info("--- Test 3: Status Normalization ---")
    statuses = [
        ("pendente", "Pendente"),
        ("  concluído  ", "Concluído"), # Title case
        (None, "Pendente")
    ]
    
    for input_val, expected in statuses:
        result = normalize_status(input_val)
        logger.info(f"Input: '{input_val}' -> Result: '{result}' (Expected: '{expected}')")
        assert result == expected, f"Falha status: {input_val} -> {result}"
        
    logger.info("=== SUCCESSO: DOMAIN CONSISTENCY VERIFIED ===")

if __name__ == '__main__':
    verify_domain()
