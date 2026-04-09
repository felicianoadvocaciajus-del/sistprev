"""
Simulador de Cenarios What-If para planejamento previdenciario.

Permite ao advogado simular alteracoes em periodos de atividade
especial e ver instantaneamente o impacto no tempo de contribuicao,
carencia, regras elegiveis e RMI.
"""
from .whatif import simular_cenario, ENDPOINT_SPEC

__all__ = [
    "simular_cenario",
    "ENDPOINT_SPEC",
]
