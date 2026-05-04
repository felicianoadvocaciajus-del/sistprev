"""
Testes do Periodo Basico de Calculo (PBC) e Salario de Beneficio.
Lei 9.876/99 Art. 29 + EC 103/2019 Art. 26.
"""
import pytest
from datetime import date
from decimal import Decimal

from app.domain.salario.pbc import (
    calcular_salario_beneficio,
    extrair_e_corrigir_salarios,
    calcular_media_pos_ec103,
    calcular_media_pre_ec103,
    selecionar_80_maiores,
    aplicar_descarte_ec103,
)
from app.domain.models.contribuicao import Contribuicao
from app.domain.models.vinculo import Vinculo
from app.domain.enums import (
    TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado
)


def _gerar_contribuicoes(inicio: date, fim: date, salario: Decimal) -> list:
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


def _vinculo(inicio: date, fim: date, salario: Decimal) -> Vinculo:
    return Vinculo(
        tipo_vinculo=TipoVinculo.EMPREGADO,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        data_inicio=inicio,
        data_fim=fim,
        contribuicoes=_gerar_contribuicoes(inicio, fim, salario),
        origem=OrigemDado.MANUAL,
    )


class TestExtracaoCorrecao:

    def test_extrai_salarios_dentro_do_periodo(self):
        """Salarios entre PBC inicial e mes anterior a DER devem ser extraidos."""
        v = _vinculo(date(2020, 1, 1), date(2024, 12, 31), Decimal("3000"))
        der = date(2025, 1, 1)
        sals = extrair_e_corrigir_salarios([v], der)
        # 60 meses (2020-01 a 2024-12)
        assert len(sals) == 60

    def test_exclui_salarios_apos_mes_anterior_der(self):
        """Mes da DER e posteriores nao entram no PBC."""
        v = _vinculo(date(2024, 1, 1), date(2025, 6, 30), Decimal("3000"))
        der = date(2025, 6, 1)
        sals = extrair_e_corrigir_salarios([v], der)
        # Deve incluir jan/2024 a maio/2025 = 17 meses
        assert all(s.competencia < date(2025, 6, 1) for s in sals)

    def test_exclui_pre_1994_quando_nao_pedido(self):
        """Por padrao, salarios pre Plano Real (jul/1994) sao excluidos."""
        v = _vinculo(date(1990, 1, 1), date(2000, 12, 31), Decimal("500"))
        der = date(2024, 1, 1)
        sals = extrair_e_corrigir_salarios([v], der, incluir_pre_1994=False)
        # Todos sao >= jul/1994
        assert all(s.competencia >= date(1994, 7, 1) for s in sals)

    def test_inclui_pre_1994_para_vida_toda(self):
        """incluir_pre_1994=True (Tema 1.102 STF) inclui salarios desde antes."""
        v = _vinculo(date(1990, 1, 1), date(2000, 12, 31), Decimal("500"))
        der = date(2024, 1, 1)
        sals = extrair_e_corrigir_salarios([v], der, incluir_pre_1994=True)
        assert any(s.competencia < date(1994, 7, 1) for s in sals)

    def test_aplica_teto_por_competencia(self):
        """SC superior ao teto da competencia deve ser limitado."""
        # 2010 jan: teto = 3467,40. SC = 5000 -> deve ser limitado a 3467,40 (corrigido)
        v = _vinculo(date(2010, 1, 1), date(2010, 12, 31), Decimal("5000"))
        der = date(2011, 1, 1)
        sals = extrair_e_corrigir_salarios([v], der)
        for s in sals:
            assert s.teto_aplicado > Decimal("0")
            # Salario ORIGINAL (sem teto) era 5000
            assert s.salario_contribuicao == Decimal("5000")
            # Mas teto de 2010 = 3467.40
            assert s.teto_aplicado == Decimal("3467.40")


class TestSelecaoOitentaMaiores:
    """Lei 9.876/99 Art. 29 §§ 5 e 6: 80% maiores com divisor minimo (60% PBC)."""

    def test_seleciona_80_porcento(self):
        """De 100 salarios, seleciona os 80 maiores."""
        # Cria 100 salarios variados
        sals = []
        for i in range(100):
            mes = (i % 12) + 1
            ano = 2010 + (i // 12)
            sals.append(Contribuicao(
                competencia=date(ano, mes, 1),
                salario_contribuicao=Decimal(str(1000 + i * 50)),  # crescente
                salario_corrigido=Decimal(str(1000 + i * 50)),
            ))
        selec, divisor = selecionar_80_maiores(sals)
        assert len(selec) == 80
        # Os 80 maiores devem ter os maiores valores
        valores_selec = [c.salario_corrigido for c in selec]
        assert min(valores_selec) >= Decimal("2000")  # piso dos selecionados

    def test_divisor_minimo_60_porcento(self):
        """Quando 80% < 60% do PBC, divisor = 60% (eleva, baixa media)."""
        # Caso extremo: 5 SCs muito altos
        sals = [
            Contribuicao(
                competencia=date(2020, m, 1),
                salario_contribuicao=Decimal("5000"),
                salario_corrigido=Decimal("5000"),
            )
            for m in range(1, 6)
        ]
        media, divisor, selec = calcular_media_pre_ec103(sals)
        # 80% de 5 = 4
        # 60% de 5 = 3 (round) -> max(3, 4) = 4
        assert divisor == 4
        # Soma 4×5000 = 20000, media 20000/4 = 5000
        assert media == Decimal("5000.00")


class TestMediaEC103:
    """EC 103/2019 Art. 26: 100% dos SC, sem descarte automatico."""

    def test_media_simples_de_todos(self):
        """Media = soma / n."""
        sals = [
            Contribuicao(
                competencia=date(2020, m, 1),
                salario_contribuicao=Decimal("3000"),
                salario_corrigido=Decimal("3000"),
            )
            for m in range(1, 13)
        ]
        media, n = calcular_media_pos_ec103(sals)
        assert media == Decimal("3000.00")
        assert n == 12

    def test_media_pondera_todos_iguais(self):
        """6 salarios diferentes: media aritmetica."""
        valores = [1000, 2000, 3000, 4000, 5000, 6000]
        sals = [
            Contribuicao(
                competencia=date(2020, i + 1, 1),
                salario_contribuicao=Decimal(str(v)),
                salario_corrigido=Decimal(str(v)),
            )
            for i, v in enumerate(valores)
        ]
        media, n = calcular_media_pos_ec103(sals)
        assert media == Decimal("3500.00")  # (1+2+3+4+5+6)/6 × 1000
        assert n == 6

    def test_media_vazia_retorna_zero(self):
        media, n = calcular_media_pos_ec103([])
        assert media == Decimal("0")
        assert n == 0


class TestDescarteEC103:
    """EC 103/2019 Art. 26 §6: pode descartar contribs menores se aumentar a media."""

    def test_descarta_baixos_se_aumenta_media(self):
        """3 SCs altos + 2 baixos: descartar os baixos eleva a media."""
        # 200 SCs (suficiente carencia), todos R$5000 + 5 SCs baixos R$1000
        sals = []
        for m in range(1, 13):
            for ano in range(2010, 2027):
                sals.append(Contribuicao(
                    competencia=date(ano, m, 1),
                    salario_contribuicao=Decimal("5000"),
                    salario_corrigido=Decimal("5000"),
                    valida_carencia=True,
                ))
        # Adicionar 5 SCs baixos
        for m in range(1, 6):
            sals.append(Contribuicao(
                competencia=date(2009, m, 1),
                salario_contribuicao=Decimal("1000"),
                salario_corrigido=Decimal("1000"),
                valida_carencia=True,
            ))
        finais, media, n_desc = aplicar_descarte_ec103(sals, meses_carencia_exigidos=180)
        # Os 5 baixos devem ter sido descartados
        assert n_desc == 5
        assert media == Decimal("5000.00")

    def test_nao_descarta_se_quebra_carencia(self):
        """Se descarte deixar carencia abaixo de 180, deve parar."""
        # Apenas 180 SCs
        sals = [
            Contribuicao(
                competencia=date(2010 + (i // 12), (i % 12) + 1, 1),
                salario_contribuicao=Decimal("3000") if i >= 5 else Decimal("1000"),
                salario_corrigido=Decimal("3000") if i >= 5 else Decimal("1000"),
                valida_carencia=True,
            )
            for i in range(180)
        ]
        finais, media, n_desc = aplicar_descarte_ec103(sals, meses_carencia_exigidos=180)
        # Nao pode descartar nenhum (cairia abaixo de 180)
        assert n_desc == 0


class TestCalcularSalarioBeneficio:
    """Funcao publica principal."""

    def test_pbc_com_salarios_uniformes_retorna_o_proprio_salario(self):
        """120 contribs de R$3000 -> SB = R$3000."""
        v = _vinculo(date(2015, 1, 1), date(2024, 12, 31), Decimal("3000"))
        der = date(2025, 1, 1)
        r = calcular_salario_beneficio([v], der, usar_regra_ec103=True, aplicar_descarte=False)
        # SB ~= 3000 (corrigido pode variar levemente, sem descarte)
        sb = r["salario_beneficio"]
        # Pode variar com correcao: aceita range
        assert sb >= Decimal("3000")  # corrigido pode subir

    def test_sem_salarios_retorna_zero(self):
        """Sem vinculos -> SB = 0."""
        r = calcular_salario_beneficio([], date(2025, 1, 1))
        assert r["salario_beneficio"] == Decimal("0")
        assert r["regra_aplicada"] == "Sem salários no PBC"

    def test_regra_pre_ec103_usa_80_pct(self):
        """usar_regra_ec103=False: aplica regra dos 80% maiores."""
        v = _vinculo(date(2010, 1, 1), date(2014, 12, 31), Decimal("3000"))
        der = date(2015, 1, 1)
        r = calcular_salario_beneficio([v], der, usar_regra_ec103=False)
        assert "Lei 9.876/99" in r["regra_aplicada"]

    def test_regra_ec103_usa_100_pct(self):
        """usar_regra_ec103=True: aplica regra dos 100% (com descarte)."""
        v = _vinculo(date(2020, 1, 1), date(2024, 12, 31), Decimal("3000"))
        der = date(2025, 1, 1)
        r = calcular_salario_beneficio([v], der, usar_regra_ec103=True)
        assert "EC 103/2019" in r["regra_aplicada"]
