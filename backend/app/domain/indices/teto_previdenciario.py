"""
Tabela do teto do RGPS por competência.
Fonte: Portarias MPS/MF/MPS/MTPS anuais.
"""
from decimal import Decimal
from datetime import date
from functools import lru_cache


def _D(s: str) -> Decimal:
    return Decimal(s)


TETO_HISTORICO = {
    (1994, 7):  _D("581.46"),
    (1995, 3):  _D("581.46"),
    (1995, 6):  _D("622.37"),
    (1996, 6):  _D("683.75"),
    (1997, 3):  _D("1031.87"),
    (1998, 3):  _D("1081.50"),
    (1998, 12): _D("1200.00"),   # EC 20/98
    (1999, 4):  _D("1255.32"),
    (2000, 6):  _D("1328.25"),
    (2001, 6):  _D("1430.00"),
    (2002, 6):  _D("1561.56"),
    (2003, 6):  _D("1869.34"),
    (2004, 1):  _D("2400.00"),   # EC 41/03
    (2004, 5):  _D("2508.72"),
    (2005, 5):  _D("2668.15"),
    (2006, 4):  _D("2801.82"),
    (2007, 4):  _D("2894.28"),
    (2008, 3):  _D("3038.99"),
    (2009, 2):  _D("3218.90"),
    (2010, 1):  _D("3467.40"),
    (2011, 1):  _D("3689.66"),
    (2012, 1):  _D("3916.20"),
    (2013, 1):  _D("4159.00"),
    (2014, 1):  _D("4390.24"),
    (2015, 1):  _D("4663.75"),
    (2016, 1):  _D("5189.82"),
    (2017, 1):  _D("5531.31"),
    (2018, 1):  _D("5645.80"),
    (2019, 1):  _D("5839.45"),
    (2020, 1):  _D("6101.06"),
    (2021, 1):  _D("6433.57"),
    (2022, 1):  _D("7087.22"),
    (2023, 1):  _D("7786.02"),
    (2024, 1):  _D("7786.02"),
    (2024, 3):  _D("7786.02"),
    (2025, 1):  _D("8157.41"),
    (2026, 1):  _D("8621.00"),
}

_CHAVES_ORDENADAS = sorted(TETO_HISTORICO.keys())


@lru_cache(maxsize=1024)
def teto_em(ano: int, mes: int) -> Decimal:
    """Retorna o teto do RGPS vigente em uma competência."""
    alvo = (ano, mes)
    vigente = None
    for chave in _CHAVES_ORDENADAS:
        if chave <= alvo:
            vigente = TETO_HISTORICO[chave]
        else:
            break
    if vigente is None:
        return TETO_HISTORICO[_CHAVES_ORDENADAS[0]]
    return vigente


def teto_na_data(d: date) -> Decimal:
    return teto_em(d.year, d.month)
