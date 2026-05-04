"""
Tabela de salário mínimo por competência.
Fonte: MTE/Portarias do Executivo Federal
Usada para: verificar contribuições abaixo do mínimo, carência de CI/facultativos.
"""
from decimal import Decimal
from datetime import date
from typing import Optional
from functools import lru_cache


def _D(s: str) -> Decimal:
    return Decimal(s)


# {(ano, mes_inicio): valor} — vale do mês_inicio até a próxima entrada
SALARIO_MINIMO_HISTORICO = {
    (1994, 7):  _D("64.79"),
    (1994, 9):  _D("70.00"),
    (1995, 5):  _D("100.00"),
    (1996, 5):  _D("112.00"),
    (1997, 5):  _D("120.00"),
    (1998, 5):  _D("130.00"),
    (1999, 5):  _D("136.00"),
    (2000, 4):  _D("151.00"),
    (2001, 4):  _D("180.00"),
    (2002, 4):  _D("200.00"),
    (2003, 4):  _D("240.00"),
    (2004, 5):  _D("260.00"),
    (2005, 5):  _D("300.00"),
    (2006, 4):  _D("350.00"),
    (2007, 4):  _D("380.00"),
    (2008, 3):  _D("415.00"),
    (2009, 2):  _D("465.00"),
    (2010, 1):  _D("510.00"),
    (2011, 3):  _D("545.00"),
    (2012, 1):  _D("622.00"),
    (2013, 1):  _D("678.00"),
    (2014, 1):  _D("724.00"),
    (2015, 1):  _D("788.00"),
    (2016, 1):  _D("880.00"),
    (2017, 1):  _D("937.00"),
    (2018, 1):  _D("954.00"),
    (2019, 1):  _D("998.00"),
    (2020, 1):  _D("1039.00"),    # Decreto 10.157/2019 (vigencia 01/01/2020)
    (2020, 2):  _D("1045.00"),    # MP 919/2020 (reajuste retroativo a 01/02/2020)
    (2021, 1):  _D("1100.00"),
    (2022, 1):  _D("1212.00"),
    (2023, 1):  _D("1302.00"),    # MP 1.143/2022 (vigencia 01/01/2023)
    (2023, 5):  _D("1320.00"),    # Lei 14.663/2023 (vigencia retroativa a 01/05/2023)
    (2024, 1):  _D("1412.00"),
    (2025, 1):  _D("1518.00"),
    (2026, 1):  _D("1623.00"),
}

_CHAVES_ORDENADAS = sorted(SALARIO_MINIMO_HISTORICO.keys())


@lru_cache(maxsize=1024)
def salario_minimo_em(ano: int, mes: int) -> Decimal:
    """Retorna o salário mínimo vigente em uma competência."""
    alvo = (ano, mes)
    vigente = None
    for chave in _CHAVES_ORDENADAS:
        if chave <= alvo:
            vigente = SALARIO_MINIMO_HISTORICO[chave]
        else:
            break
    if vigente is None:
        # Para competências antes de jul/1994, usar o valor mais antigo da tabela
        return SALARIO_MINIMO_HISTORICO[_CHAVES_ORDENADAS[0]]
    return vigente


def salario_minimo_na_data(d: date) -> Decimal:
    return salario_minimo_em(d.year, d.month)
