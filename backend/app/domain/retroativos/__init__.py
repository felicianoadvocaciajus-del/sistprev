"""
Modulo de Calculo de Retroativos Previdenciarios.

Calcula valores devidos pelo INSS ao segurado em casos de:
  - Concessao tardia de beneficio
  - Revisao de beneficio (RMI recalculada)
  - Indeferimento indevido

Exporta:
  - calcular_retroativos: funcao principal do motor
  - calcular_correcao_monetaria: correcao INPC isolada
  - calcular_juros_mora: juros de mora isolados
  - ParcelaRetroativa: dataclass de uma parcela mensal
  - ResultadoRetroativos: dataclass do resultado consolidado
"""

from .motor_retroativos import (
    calcular_retroativos,
    calcular_correcao_monetaria,
    calcular_juros_mora,
    ParcelaRetroativa,
    ResultadoRetroativos,
)

__all__ = [
    "calcular_retroativos",
    "calcular_correcao_monetaria",
    "calcular_juros_mora",
    "ParcelaRetroativa",
    "ResultadoRetroativos",
]
