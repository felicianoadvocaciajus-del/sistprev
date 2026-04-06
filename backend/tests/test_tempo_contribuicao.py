"""
Testes do módulo de contagem de Tempo de Contribuição.
"""
import pytest
from datetime import date
from decimal import Decimal
from app.domain.models.vinculo import Vinculo
from app.domain.models.contribuicao import Contribuicao, Competencia
from app.domain.enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado, Sexo
from app.domain.tempo.contagem import calcular_tempo_contribuicao, calcular_carencia


def _vinculo(inicio: date, fim: date, contribuicoes=None) -> Vinculo:
    if contribuicoes is None:
        contribuicoes = []
    return Vinculo(
        tipo_vinculo=TipoVinculo.EMPREGADO,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        data_inicio=inicio,
        data_fim=fim,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
    )


def _contrib_range(inicio: date, fim: date, salario: Decimal = Decimal("2000")) -> list:
    """Gera competências mensais entre início e fim."""
    result = []
    atual = date(inicio.year, inicio.month, 1)
    fim_comp = date(fim.year, fim.month, 1)
    while atual <= fim_comp:
        result.append(Contribuicao(competencia=atual, salario_contribuicao=salario))
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)
    return result


class TestContagem:
    def test_vinculo_10_anos(self):
        """10 anos contínuos devem resultar em ~3650 dias."""
        inicio = date(2010, 1, 1)
        fim = date(2019, 12, 31)
        contribs = _contrib_range(inicio, fim)
        v = _vinculo(inicio, fim, contribs)
        der = date(2020, 1, 1)
        tc = calcular_tempo_contribuicao([v], der, Sexo.MASCULINO)
        assert tc.anos == 10
        assert tc.total_dias > 3600

    def test_vinculo_zero_dias(self):
        """Vínculo de 1 dia não deve contar TC significativo."""
        inicio = date(2020, 1, 1)
        v = _vinculo(inicio, inicio, [])
        der = date(2020, 12, 31)
        tc = calcular_tempo_contribuicao([v], der, Sexo.MASCULINO)
        assert tc.total_dias <= 1

    def test_sobreposicao_nao_duplica(self):
        """Dois vínculos sobrepostos não devem duplicar o tempo."""
        inicio = date(2010, 1, 1)
        fim = date(2015, 12, 31)
        c1 = _contrib_range(inicio, fim)
        c2 = _contrib_range(date(2013, 1, 1), date(2017, 12, 31))
        v1 = _vinculo(inicio, fim, c1)
        v2 = _vinculo(date(2013, 1, 1), date(2017, 12, 31), c2)
        der = date(2018, 1, 1)
        tc = calcular_tempo_contribuicao([v1, v2], der, Sexo.MASCULINO)
        # Período real: jan/2010 a dez/2017 = 8 anos
        assert tc.anos == 8
        assert tc.anos < 13  # não somou simplesmente

    def test_contribuicoes_contam_carencia(self):
        """Carência deve contar competências, não dias."""
        inicio = date(2020, 1, 1)
        fim = date(2021, 12, 31)
        contribs = _contrib_range(inicio, fim)
        v = _vinculo(inicio, fim, contribs)
        der = date(2022, 1, 1)
        carencia = calcular_carencia([v], der)
        assert carencia == 24  # 24 meses


class TestTempoEspecial:
    def test_atividade_especial_25_converte(self):
        """Atividade especial 25 anos deve ser multiplicada pelo fator de conversão."""
        inicio = date(2000, 1, 1)
        fim = date(2009, 12, 31)
        contribs = _contrib_range(inicio, fim)
        v = Vinculo(
            tipo_vinculo=TipoVinculo.EMPREGADO,
            regime=RegimePrevidenciario.RGPS,
            tipo_atividade=TipoAtividade.ESPECIAL_25,
            data_inicio=inicio,
            data_fim=fim,
            contribuicoes=contribs,
            origem=OrigemDado.MANUAL,
        )
        der = date(2010, 1, 1)
        tc = calcular_tempo_contribuicao([v], der, Sexo.MASCULINO, incluir_especial=True)
        # 10 anos especial_25 convertidos para ~14 anos comuns (fator 1.4)
        assert tc.anos >= 13
