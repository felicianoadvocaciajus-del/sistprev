"""
Fator Previdenciário — Lei 9.876/1999 Art. 29-B e Decreto 3.048/99 Art. 32.

Fórmula:
    f = (Tc × a / Es) × [1 + (Id + Tc × a) / 100]

Onde:
    Tc = tempo de contribuição em anos (com decimais)
    a  = 0,31 (alíquota atuarial — fixo por lei)
    Es = expectativa de sobrevida na data da aposentadoria (tábua IBGE do ano)
    Id = idade na data da aposentadoria (em anos, com decimais)

Nota: o FP pode ser < 1 (penaliza quem se aposenta cedo) ou > 1 (bonifica quem adia).
      Após EC 103/2019, o FP só é obrigatório na regra do Pedágio 50% (Art. 17).
      Para as demais regras de transição e regra permanente, usa-se o coeficiente (60%+2%).

Coeficiente EC 103/2019 — Art. 26:
    RMI = SB × [60% + 2% × (anos_TC - limiar)]
    limiar = 20 anos (H) ou 15 anos (M) para aposentadoria programada
    Máximo = 100% do SB
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Optional

from .indices.expectativa_sobrevida import expectativa_sobrevida
from .constantes import (
    ALIQUOTA_ATUARIAL,
    COEFICIENTE_BASE, COEFICIENTE_INCREMENTO, COEFICIENTE_MAXIMO,
    COEFICIENTE_LIMIAR_HOMEM, COEFICIENTE_LIMIAR_MULHER,
)
from .enums import Sexo


def calcular_fator_previdenciario(
    tc_anos: Decimal,
    idade_anos: Decimal,
    der: date,
) -> Decimal:
    """
    Calcula o Fator Previdenciário conforme Lei 9.876/99.

    tc_anos: tempo de contribuição em anos decimais (ex: 35.5)
    idade_anos: idade na DER em anos decimais (ex: 57.3)
    der: data de entrada do requerimento (define qual tábua IBGE usar)

    Retorna o fator com 4 casas decimais (arredondamento ROUND_HALF_UP).
    """
    a = ALIQUOTA_ATUARIAL  # 0,31

    # Expectativa de sobrevida da tábua IBGE do ano da DER
    # Usa a idade inteira (por anos completos) — conforme Decreto 3.048/99
    idade_int = int(idade_anos.to_integral_value(rounding=ROUND_HALF_UP))
    es = expectativa_sobrevida(idade_int, der.year)

    if es <= Decimal("0"):
        return Decimal("1")

    # f = (Tc × a / Es) × [1 + (Id + Tc × a) / 100]
    tc_x_a = tc_anos * a
    fator = (tc_x_a / es) * (Decimal("1") + (idade_anos + tc_x_a) / Decimal("100"))

    return fator.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calcular_coeficiente(
    tc_anos: Decimal,
    sexo: Sexo,
    tipo_beneficio_limiar: Optional[str] = "aposentadoria",
) -> Decimal:
    """
    Calcula o coeficiente da RMI conforme EC 103/2019 Art. 26.

    Base = 60%
    Incremento = +2% por ano de contribuição acima do limiar
    Limiar = 20 anos (H) / 15 anos (M) para aposentadoria por idade/TC
    Máximo = 100%

    Retorna o coeficiente como Decimal (ex: Decimal("0.80") = 80%).
    """
    if sexo == Sexo.MASCULINO:
        limiar = COEFICIENTE_LIMIAR_HOMEM  # 20 anos
    else:
        limiar = COEFICIENTE_LIMIAR_MULHER  # 15 anos

    anos_excedentes = max(Decimal("0"), tc_anos - limiar)
    coeficiente = COEFICIENTE_BASE + COEFICIENTE_INCREMENTO * anos_excedentes

    # Limitar ao máximo de 100%
    coeficiente = min(coeficiente, COEFICIENTE_MAXIMO)

    return coeficiente.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def rmi_com_fator(
    salario_beneficio: Decimal,
    fator: Decimal,
    teto: Decimal,
) -> Decimal:
    """Aplica o fator previdenciário ao SB e limita ao teto."""
    rmi = salario_beneficio * fator
    rmi = rmi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(rmi, teto)


def rmi_com_coeficiente(
    salario_beneficio: Decimal,
    coeficiente: Decimal,
    teto: Decimal,
    piso: Optional[Decimal] = None,
) -> Decimal:
    """Aplica o coeficiente ao SB, limita ao teto e respeita o piso (salário mínimo)."""
    rmi = salario_beneficio * coeficiente
    rmi = rmi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rmi = min(rmi, teto)
    if piso:
        rmi = max(rmi, piso)
    return rmi


def anos_para_100_porcento(tc_atual_anos: Decimal, sexo: Sexo) -> Decimal:
    """
    Calcula quantos anos faltam para atingir coeficiente de 100%.
    Útil para planejamento previdenciário.
    """
    if sexo == Sexo.MASCULINO:
        limiar = COEFICIENTE_LIMIAR_HOMEM  # 20
        anos_para_100 = limiar + Decimal("20")  # 40 anos TC = 60% + 2%×20 = 100%
    else:
        limiar = COEFICIENTE_LIMIAR_MULHER  # 15
        anos_para_100 = limiar + Decimal("20")  # 35 anos TC = 60% + 2%×20 = 100%

    return max(Decimal("0"), anos_para_100 - tc_atual_anos)
