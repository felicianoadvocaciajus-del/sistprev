"""
Testes do módulo de liquidação de sentença (parcelas atrasadas).
"""
import pytest
from datetime import date
from decimal import Decimal
from app.revisoes.liquidacao_sentenca import calcular_atrasados


class TestLiquidacao:
    def test_parcelas_contagem_correta(self):
        """DIB jan/2020, atualização jan/2024 = 48 competências."""
        r = calcular_atrasados(
            dib=date(2020, 1, 1),
            rmi_original=Decimal("2000"),
            data_atualizacao=date(2024, 1, 1),
            incluir_juros=False,
        )
        assert r["parcelas_calculadas"] == 48

    def test_total_sem_juros_igual_soma_parcelas(self):
        r = calcular_atrasados(
            dib=date(2023, 1, 1),
            rmi_original=Decimal("2500"),
            data_atualizacao=date(2023, 12, 1),
            incluir_juros=False,
        )
        soma = sum(Decimal(str(p["valor_corrigido"])) for p in r["parcelas"])
        assert abs(soma - r["total_principal"]) < Decimal("0.05")

    def test_juros_aumentam_total(self):
        """Com juros, total geral deve ser maior que apenas principal."""
        sem_juros = calcular_atrasados(
            dib=date(2015, 1, 1),
            rmi_original=Decimal("1500"),
            data_atualizacao=date(2023, 12, 1),
            incluir_juros=False,
        )
        com_juros = calcular_atrasados(
            dib=date(2015, 1, 1),
            rmi_original=Decimal("1500"),
            data_atualizacao=date(2023, 12, 1),
            incluir_juros=True,
        )
        assert com_juros["total_geral"] > sem_juros["total_geral"]

    def test_prescricao_quinquenal(self):
        """Parcelas há mais de 5 anos do ajuizamento devem ser excluídas."""
        r = calcular_atrasados(
            dib=date(2010, 1, 1),
            rmi_original=Decimal("1200"),
            data_atualizacao=date(2023, 12, 1),
            data_ajuizamento=date(2022, 1, 1),
        )
        # DIB jan/2010, ajuizamento jan/2022: prescrição de jan/2010 a jan/2017 = 84 meses
        assert r["parcelas_prescritas"] == 84

    def test_sem_prescricao_quando_sem_ajuizamento(self):
        """Sem data de ajuizamento, nenhuma parcela é prescrita."""
        r = calcular_atrasados(
            dib=date(2000, 1, 1),
            rmi_original=Decimal("800"),
            data_atualizacao=date(2010, 1, 1),
        )
        assert r["parcelas_prescritas"] == 0
        assert r["parcelas_calculadas"] == 120  # 10 anos × 12

    def test_valor_corrigido_maior_que_base(self):
        """Para períodos antigos, valor corrigido > valor base."""
        r = calcular_atrasados(
            dib=date(2010, 1, 1),
            rmi_original=Decimal("1500"),
            data_atualizacao=date(2023, 12, 1),
        )
        primeira = r["parcelas"][0]
        assert Decimal(str(primeira["valor_corrigido"])) > Decimal(str(primeira["valor_base"]))

    def test_selic_pos_ec113(self):
        """Parcelas a partir de jan/2022 devem usar SELIC."""
        r = calcular_atrasados(
            dib=date(2022, 1, 1),
            rmi_original=Decimal("1412"),
            data_atualizacao=date(2023, 12, 1),
            incluir_juros=True,
        )
        # Com SELIC, deve haver juros positivos
        assert r["total_juros"] > Decimal("0")
