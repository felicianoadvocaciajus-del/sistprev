"""
Testes do módulo de correção monetária.

Casos de referência tirados de tabelas do Tribunal Regional Federal
e do Índice Geral de Preços da FGV.
"""
import pytest
from decimal import Decimal
from app.domain.indices.correcao_monetaria import fator_acumulado, corrigir_salario


class TestFatorAcumulado:
    def test_mesmo_periodo_retorna_1(self):
        """Fator de um mês para o mesmo mês deve ser 1."""
        f = fator_acumulado((2020, 1), (2020, 1))
        assert f == Decimal("1")

    def test_fator_positivo(self):
        """Fator de correção deve ser maior que 1 para períodos históricos."""
        f = fator_acumulado((2000, 1), (2023, 12))
        assert f > Decimal("1")

    def test_fator_cresce_com_tempo(self):
        """Fator de período maior deve ser maior que fator de período menor."""
        f10 = fator_acumulado((2010, 1), (2023, 1))
        f5 = fator_acumulado((2015, 1), (2023, 1))
        assert f10 > f5

    def test_fator_invertido_menor_que_1(self):
        """Fator com data início > data fim deve ser menor que 1."""
        f = fator_acumulado((2023, 1), (2015, 1))
        assert f < Decimal("1")

    def test_periodo_inpc_recente(self):
        """Correção de 2022 a 2024 com valores plausíveis."""
        f = fator_acumulado((2022, 1), (2024, 1))
        # Em 2022-2024 a inflação acumulada ficou em torno de 10-15%
        assert Decimal("1.05") < f < Decimal("1.30")

    def test_corrigir_salario_simples(self):
        """Salário de R$1000 em jan/2000 deve valer muito mais em 2023."""
        from datetime import date
        valor = corrigir_salario(
            Decimal("1000"),
            date(2000, 1, 1),
            date(2023, 12, 1)
        )
        assert valor > Decimal("3000")  # inflação acumulada significativa

    def test_corrigir_salario_sem_variacao(self):
        """Salário no mesmo mês deve retornar o mesmo valor."""
        from datetime import date
        valor = corrigir_salario(
            Decimal("2500"),
            date(2020, 6, 1),
            date(2020, 6, 1)
        )
        assert valor == Decimal("2500")


class TestCacheFatorAcumulado:
    def test_cache_consistente(self):
        """Duas chamadas com os mesmos parâmetros devem retornar o mesmo valor."""
        f1 = fator_acumulado((2010, 3), (2020, 9))
        f2 = fator_acumulado((2010, 3), (2020, 9))
        assert f1 == f2
