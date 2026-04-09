"""
Modulo Detetive Previdenciario

Motor de cruzamento automatico que compara dados de multiplos documentos
(CNIS, CTPS, PPP, LTCAT, Carta de Concessao) para identificar
oportunidades previdenciarias.
"""

from .cruzamento import analisar_cruzamento

__all__ = [
    "analisar_cruzamento",
]
