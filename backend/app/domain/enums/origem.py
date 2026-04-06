from enum import Enum


class OrigemDado(str, Enum):
    CNIS = "CNIS"
    CTPS = "CTPS"
    CARTA_CONCESSAO = "CARTA_CONCESSAO"
    MANUAL = "MANUAL"
