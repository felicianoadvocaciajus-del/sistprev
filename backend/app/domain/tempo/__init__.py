from .contagem import calcular_tempo_contribuicao, calcular_carencia, identificar_sobreposicoes
from .qualidade_segurado import verificar_qualidade_segurado
from .conversao_especial import fator_conversao, converter_dias_especiais

__all__ = [
    "calcular_tempo_contribuicao",
    "calcular_carencia",
    "identificar_sobreposicoes",
    "verificar_qualidade_segurado",
    "fator_conversao",
    "converter_dias_especiais",
]
