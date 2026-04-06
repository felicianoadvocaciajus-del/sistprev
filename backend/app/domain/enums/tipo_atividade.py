from enum import Enum


class TipoAtividade(str, Enum):
    """
    Classifica a atividade quanto à nocividade.
    Determina o fator de conversão aplicado ao tempo especial.
    """
    NORMAL = "NORMAL"               # Atividade comum

    ESPECIAL_15 = "ESPECIAL_15"     # Especial com aposent. em 15 anos (agentes biológicos, etc.)
    ESPECIAL_20 = "ESPECIAL_20"     # Especial com aposent. em 20 anos (mineração subterrânea, etc.)
    ESPECIAL_25 = "ESPECIAL_25"     # Especial com aposent. em 25 anos (ruído, calor, agentes químicos, etc.)
