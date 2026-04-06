"""
Verificação da qualidade de segurado (Art. 15 Lei 8.213/91).

O segurado mantém a qualidade mesmo após cessar os recolhimentos,
durante um "período de graça" que varia conforme o tipo de vínculo.
"""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from ..models.vinculo import Vinculo
from ..enums import TipoVinculo, RegimePrevidenciario
from ..constantes import PeriodoGraca


def verificar_qualidade_segurado(
    vinculos: List[Vinculo],
    data_referencia: date,
    num_contribuicoes_sem_interrupcao: int = 0,
    desemprego_involuntario_comprovado: bool = False,
) -> Tuple[bool, Optional[date], str]:
    """
    Verifica se o segurado mantém a qualidade na data de referência.

    Retorna:
        (tem_qualidade: bool, data_perda: Optional[date], justificativa: str)

    data_perda = None se nunca perdeu ou ainda não perdeu
    """
    if not vinculos:
        return False, None, "Nenhum vínculo contributivo encontrado."

    # Encontrar a última data de contribuição ou vínculo em aberto
    ultima_contribuicao: Optional[date] = None
    tipo_ultimo_vinculo: Optional[TipoVinculo] = None
    vinculo_em_aberto = False

    for v in sorted(vinculos, key=lambda x: x.data_inicio):
        if v.regime != RegimePrevidenciario.RGPS:
            continue
        if v.is_em_aberto:
            vinculo_em_aberto = True
            tipo_ultimo_vinculo = v.tipo_vinculo
        if v.contribuicoes:
            ultima_comp = max(c.competencia for c in v.contribuicoes if c.valida_carencia)
            if ultima_contribuicao is None or ultima_comp > ultima_contribuicao:
                ultima_contribuicao = ultima_comp
                tipo_ultimo_vinculo = v.tipo_vinculo

    # Segurado com vínculo em aberto mantém a qualidade
    if vinculo_em_aberto:
        return True, None, "Segurado com vínculo empregatício em aberto."

    if ultima_contribuicao is None:
        return False, None, "Não foram encontradas contribuições válidas."

    # Determinar período de graça conforme tipo de vínculo
    meses_graca = _periodo_graca(
        tipo_ultimo_vinculo,
        num_contribuicoes_sem_interrupcao,
        desemprego_involuntario_comprovado,
    )

    # Calcular data de perda da qualidade
    data_perda = _somar_meses(ultima_contribuicao, meses_graca)

    if data_referencia <= data_perda:
        justif = (
            f"Mantém qualidade até {data_perda.strftime('%m/%Y')} "
            f"({meses_graca} meses de graça após {ultima_contribuicao.strftime('%m/%Y')})."
        )
        return True, data_perda, justif
    else:
        justif = (
            f"Perdeu a qualidade de segurado em {data_perda.strftime('%m/%Y')} "
            f"(último recolhimento: {ultima_contribuicao.strftime('%m/%Y')}, "
            f"graça: {meses_graca} meses)."
        )
        return False, data_perda, justif


def _periodo_graca(
    tipo: Optional[TipoVinculo],
    num_contribuicoes: int,
    desemprego_involuntario: bool,
) -> int:
    """Retorna o período de graça em meses conforme Art. 15 Lei 8.213/91."""
    if tipo in (TipoVinculo.EMPREGADO, TipoVinculo.EMPREGADO_DOMESTICO,
                TipoVinculo.TRABALHADOR_AVULSO):
        if desemprego_involuntario and num_contribuicoes >= 120:
            return PeriodoGraca.EMPREGADO_DESEMPREGADO  # 36 meses
        elif num_contribuicoes >= 120:
            return PeriodoGraca.EMPREGADO_EXTENSAO       # 24 meses
        else:
            return PeriodoGraca.EMPREGADO_BASE           # 12 meses

    elif tipo in (TipoVinculo.CONTRIBUINTE_INDIVIDUAL, TipoVinculo.FACULTATIVO,
                  TipoVinculo.MEI):
        return PeriodoGraca.CI_FACULTATIVO  # 6 meses

    elif tipo == TipoVinculo.TRABALHADOR_AVULSO:
        return PeriodoGraca.AVULSO  # 12 meses

    # Para outros tipos, usar o mínimo
    return PeriodoGraca.EMPREGADO_BASE


def _somar_meses(d: date, meses: int) -> date:
    """Soma meses a uma date, retornando o último dia do mês resultante."""
    mes = d.month + meses
    ano = d.year + (mes - 1) // 12
    mes = ((mes - 1) % 12) + 1
    # Último dia do mês
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, ultimo_dia)
