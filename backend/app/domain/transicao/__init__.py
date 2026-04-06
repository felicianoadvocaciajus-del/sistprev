from .comparador import comparar_todas, melhor_regra
from .regras import (
    RegraPonitosProgressivos, RegraIdadeProgressiva,
    RegraPedagio50, RegraPedagio100, RegraDireitoAdquirido,
)

__all__ = [
    "comparar_todas", "melhor_regra",
    "RegraPonitosProgressivos", "RegraIdadeProgressiva",
    "RegraPedagio50", "RegraPedagio100", "RegraDireitoAdquirido",
]
