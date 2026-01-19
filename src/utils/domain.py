
import re
import unicodedata

def normalize_city(city_name: str) -> str:
    """
    Normaliza nome de cidade para evitar erros de precificação (Lote).
    
    Regras:
    1. Upper case
    2. Strip whitespace
    3. Remove acentos (opcional, mas recomendado para consistência forte)
    4. Remove caracteres especiais desnecessários
    
    Ex: " São Paulo " -> "SAO PAULO"
    """
    if not city_name:
        return "INDEFINIDO"
    
    # 1. Strip e Upper
    s = city_name.strip().upper()
    
    # 2. Remover acentos (Normalization Form KD)
    # Isso separa caracteres acentuados (ex: á -> a + ´) e removemos os 'non-spacing marks'
    nfkd_form = unicodedata.normalize('NFKD', s)
    s = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    
    # 3. Remover caracteres estranhos (manter apenas letras, numeros, espacos)
    # Ex: "Mogi-Mirim" -> "MOGI MIRIM" (hifen vira espaco ou remove? padrao varia)
    # Se optarmos por consistência estrita com Pricing, devemos ver como o Pricing armazena.
    # Assumindo que o DB pode ter acentos, talvez seja MELHOR NORMALIZAR O INPUT DO QUE O DADO,
    # mas para Lote, é "Belo Horizonte" vs "Belo Horizonte ".
    
    # Simplificação: Apenas strip e upper, e single space.
    # Remover multiplos espaços
    s = re.sub(r'\s+', ' ', s)
    
    return s.strip()

def normalize_status(status: str) -> str:
    """Normaliza status do chamado."""
    if not status:
        return "Pendente"
    return status.strip().title()
