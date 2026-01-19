"""
Utilitários de serialização para valores monetários.

Garante que todos os valores monetários sejam serializados consistentemente
como strings com 2 casas decimais, evitando:
- Decimal cru em JSON (TypeError)
- Conversão para float (perda de precisão)
"""

from decimal import Decimal, ROUND_HALF_UP

# Constante para arredondamento
TWO_PLACES = Decimal('0.01')


def money_str(value) -> str:
    """
    Converte valor monetário para string com exatamente 2 casas decimais.
    
    Args:
        value: Valor a converter (Decimal, float, int, str ou None)
    
    Returns:
        String formatada com 2 casas decimais (ex: "120.00")
    
    Examples:
        >>> money_str(None)
        '0.00'
        >>> money_str(120)
        '120.00'
        >>> money_str(Decimal('123.456'))
        '123.46'
        >>> money_str(99.9)
        '99.90'
    """
    if value is None:
        return '0.00'
    
    if isinstance(value, Decimal):
        return str(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))
    
    # Converter para Decimal primeiro para garantir precisão
    try:
        decimal_value = Decimal(str(value))
        return str(decimal_value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))
    except (ValueError, TypeError):
        return '0.00'


def to_decimal(value) -> Decimal:
    """
    Converte valor para Decimal de forma segura.
    
    Use em cálculos internos para evitar mistura de float com Decimal.
    
    Args:
        value: Valor a converter (Decimal, float, int, str ou None)
    
    Returns:
        Decimal (0 se valor for None ou inválido)
    """
    if value is None:
        return Decimal('0')
    
    if isinstance(value, Decimal):
        return value
    
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal('0')


def percent_str(value, decimals: int = 1) -> str:
    """
    Formata valor percentual como string.
    
    Args:
        value: Valor percentual
        decimals: Casas decimais (default: 1)
    
    Returns:
        String formatada (ex: "15.5")
    """
    if value is None:
        return '0.0'
    
    try:
        return str(round(float(value), decimals))
    except (ValueError, TypeError):
        return '0.0'
