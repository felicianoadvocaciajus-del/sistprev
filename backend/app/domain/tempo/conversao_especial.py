"""
Conversão de tempo especial para tempo comum.
Art. 57 Lei 8.213/91 e Art. 70 Decreto 3.048/99.

Fatores de conversão (tempo especial → tempo comum necessário):
  15 anos especiais → 35 anos comuns (H): fator 7/3  ≈ 2,333
  15 anos especiais → 30 anos comuns (F): fator 2,0
  20 anos especiais → 35 anos comuns (H): fator 7/4  = 1,75
  20 anos especiais → 30 anos comuns (F): fator 3/2  = 1,5
  25 anos especiais → 35 anos comuns (H): fator 7/5  = 1,4
  25 anos especiais → 30 anos comuns (F): fator 6/5  = 1,2

REGRA: Conversão especial → comum é válida para períodos até 13/11/2019.
       A EC 103/2019 (Art. 25, §2º) proibiu a conversão para períodos
       trabalhados APÓS 13/11/2019.
       O STJ (Tema 422, REsp 1.310.034) pacificou que a conversão vale
       para TODO período especial anterior a 13/11/2019.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Optional

from ..enums import TipoAtividade, Sexo
from ..constantes import FATORES_CONVERSAO, DATA_LIMITE_CONVERSAO_ESPECIAL


def fator_conversao(
    tipo_atividade: TipoAtividade,
    sexo: Sexo,
) -> Decimal:
    """
    Retorna o fator de conversão de tempo especial para tempo comum.
    Conforme Decreto 3.048/99 Art. 70 Tabela 1.
    """
    if tipo_atividade == TipoAtividade.NORMAL:
        return Decimal("1")
    chave = (tipo_atividade.value, sexo.value)
    return FATORES_CONVERSAO.get(chave, Decimal("1"))


def converter_dias_especiais(
    dias_especiais: int,
    tipo_atividade: TipoAtividade,
    sexo: Sexo,
    data_fim_periodo: Optional[date] = None,
) -> int:
    """
    Converte dias de tempo especial em dias equivalentes de tempo comum.

    dias_especiais: número de dias de atividade especial
    tipo_atividade: qual categoria especial (15, 20 ou 25 anos)
    sexo: para determinar qual TC mínimo usar (35H/30M)
    data_fim_periodo: data de fim do período especial (para verificar validade)

    Retorna os dias convertidos (arredondamento para cima).
    """
    f = fator_conversao(tipo_atividade, sexo)
    dias_convertidos = Decimal(str(dias_especiais)) * f
    return int(dias_convertidos.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pode_converter(data_inicio: date, data_fim: date) -> bool:
    """
    Verifica se um período especial pode ser convertido para tempo comum.
    A conversão só é válida para períodos até 13/11/2019 (limite EC 103/2019).

    Após essa data: o segurado pode aposentar com tempo especial, mas não
    converte o especial em tempo comum para outros fins.
    """
    # Períodos que terminam antes do limite podem ser convertidos
    if data_fim <= DATA_LIMITE_CONVERSAO_ESPECIAL:
        return True
    # Períodos que iniciam e terminam após o limite: não podem converter
    if data_inicio > DATA_LIMITE_CONVERSAO_ESPECIAL:
        return False
    # Período parcialmente anterior ao limite: apenas a parte anterior converte
    return True  # o cálculo parcial é feito em calcular_dias_convertidos_parcial


def calcular_dias_convertidos_parcial(
    data_inicio: date,
    data_fim: date,
    tipo_atividade: TipoAtividade,
    sexo: Sexo,
) -> int:
    """
    Para períodos que cruzam a data limite (13/11/2019):
    - Dias antes do limite: convertidos com fator
    - Dias após o limite: contados em 1:1 (apenas para aposentadoria especial)

    Retorna o total de dias convertidos para efeito de TC.
    """
    limite = DATA_LIMITE_CONVERSAO_ESPECIAL

    if data_fim <= limite:
        # Todo o período é convertível
        dias = (data_fim - data_inicio).days + 1
        return converter_dias_especiais(dias, tipo_atividade, sexo)

    if data_inicio > limite:
        # Nenhum dia é convertível; retorna dias em 1:1
        return (data_fim - data_inicio).days + 1

    # Período misto: parte antes e parte depois
    dias_antes = (limite - data_inicio).days + 1
    dias_depois = (data_fim - limite).days
    dias_convertidos = converter_dias_especiais(dias_antes, tipo_atividade, sexo)
    return dias_convertidos + dias_depois
