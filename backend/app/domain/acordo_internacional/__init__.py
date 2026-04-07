"""
Modulo de acordos internacionais de previdencia social.

Implementa totalizacao de tempo de contribuicao entre o Brasil e paises
signatarios de acordos bilaterais e multilaterais, com calculo de
proporcionalidade (pro-rata temporis).

Uso basico:
    >>> from app.domain.acordo_internacional import verificar_acordo, calcular_totalizacao
    >>> acordo = verificar_acordo("Espanha")
    >>> acordo.decreto
    'Decreto 1.689/1995'
"""

from .motor_acordo import (
    AcordoInternacional,
    PeriodoExterior,
    ResultadoTotalizacao,
    verificar_acordo,
    calcular_totalizacao,
    documentos_necessarios,
    listar_acordos,
)

__all__ = [
    "AcordoInternacional",
    "PeriodoExterior",
    "ResultadoTotalizacao",
    "verificar_acordo",
    "calcular_totalizacao",
    "documentos_necessarios",
    "listar_acordos",
]
