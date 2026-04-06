from enum import Enum


class RegimePrevidenciario(str, Enum):
    RGPS = "RGPS"   # Regime Geral de Previdência Social (INSS)
    RPPS = "RPPS"   # Regime Próprio de Previdência Social (servidores)
    MILITAR = "MILITAR"
