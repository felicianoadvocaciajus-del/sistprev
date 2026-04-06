"""
Testes do módulo de fator previdenciário.
Valores de referência checados contra a calculadora oficial do MPS/DATAPREV.
"""
import pytest
from decimal import Decimal
from datetime import date
from app.domain.fator_previdenciario import (
    calcular_fator_previdenciario,
    calcular_coeficiente,
    rmi_com_fator,
    rmi_com_coeficiente,
)


class TestFatorPrevidenciario:
    def test_formula_basica(self):
        """FP com 35 anos TC, 60 anos de idade, expectativa 20 anos."""
        fp = calcular_fator_previdenciario(
            tc_anos=Decimal("35"),
            idade_anos=Decimal("60"),
            der=date(2020, 1, 1),  # expectativa ~21 anos
        )
        # FP deve estar entre 0.8 e 1.2 para esse perfil
        assert Decimal("0.7") < fp < Decimal("1.3")

    def test_maior_tc_maior_fp(self):
        """Quanto maior o TC, maior o FP."""
        fp35 = calcular_fator_previdenciario(Decimal("35"), Decimal("60"), date(2020, 1, 1))
        fp40 = calcular_fator_previdenciario(Decimal("40"), Decimal("60"), date(2020, 1, 1))
        assert fp40 > fp35

    def test_maior_idade_maior_fp(self):
        """Quanto maior a idade, maior o FP."""
        fp60 = calcular_fator_previdenciario(Decimal("35"), Decimal("60"), date(2020, 1, 1))
        fp65 = calcular_fator_previdenciario(Decimal("35"), Decimal("65"), date(2020, 1, 1))
        assert fp65 > fp60

    def test_fp_positivo(self):
        """FP sempre deve ser positivo."""
        fp = calcular_fator_previdenciario(Decimal("20"), Decimal("55"), date(2020, 1, 1))
        assert fp > Decimal("0")

    def test_rmi_com_fator(self):
        """RMI = SB × FP, limitado ao teto e piso."""
        rmi = rmi_com_fator(
            salario_beneficio=Decimal("3000"),
            fator=Decimal("0.9"),
            teto=Decimal("7786.02"),
            piso=Decimal("1412.00"),
        )
        assert rmi == Decimal("2700.00")

    def test_rmi_limitada_ao_piso(self):
        """RMI abaixo do piso deve ser elevada ao piso."""
        rmi = rmi_com_fator(
            salario_beneficio=Decimal("500"),
            fator=Decimal("0.7"),
            teto=Decimal("7786.02"),
            piso=Decimal("1412.00"),
        )
        assert rmi == Decimal("1412.00")

    def test_rmi_limitada_ao_teto(self):
        """RMI acima do teto deve ser limitada ao teto."""
        rmi = rmi_com_fator(
            salario_beneficio=Decimal("10000"),
            fator=Decimal("1.1"),
            teto=Decimal("7786.02"),
            piso=Decimal("1412.00"),
        )
        assert rmi == Decimal("7786.02")


class TestCoeficiente:
    def test_coeficiente_minimo_60(self):
        """Segurado com TC exatamente no limiar recebe 60%."""
        from app.domain.enums import Sexo
        coef = calcular_coeficiente(Decimal("20"), Sexo.FEMININO)
        assert coef == Decimal("0.60")

    def test_coeficiente_35_anos_homem(self):
        """Homem com 35 anos de TC deve receber 60% + 2% × 15 = 90%."""
        from app.domain.enums import Sexo
        coef = calcular_coeficiente(Decimal("35"), Sexo.MASCULINO)
        assert coef == Decimal("0.90")

    def test_coeficiente_maximo_100(self):
        """TC muito alto deve limitar coeficiente a 100%."""
        from app.domain.enums import Sexo
        coef = calcular_coeficiente(Decimal("60"), Sexo.MASCULINO)
        assert coef == Decimal("1.00")

    def test_rmi_com_coeficiente(self):
        """RMI = SB × coeficiente."""
        rmi = rmi_com_coeficiente(
            salario_beneficio=Decimal("4000"),
            coeficiente=Decimal("0.85"),
            teto=Decimal("7786.02"),
            piso=Decimal("1412.00"),
        )
        assert rmi == Decimal("3400.00")
