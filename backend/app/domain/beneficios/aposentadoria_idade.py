"""
Aposentadoria por Idade — Espécies B41 (urbana) e B42 (rural).

Regra permanente pós-EC 103/2019:
  Homem: 65 anos + 20 anos TC (mínimo)
  Mulher: 62 anos + 15 anos TC (mínimo)
  Carência: 180 contribuições mensais

RMI = SB × coeficiente (60% + 2% por ano acima do limiar)
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .base import CalculadoraBeneficio
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra, ResultadoRequisitos, MemoriaCalculo, DispositivoLegal
from ..enums import TipoBeneficio, Sexo
from ..constantes import Carencia, DatasCorte, IDADE_DEFINITIVA_HOMEM, IDADE_DEFINITIVA_MULHER
from ..tempo import calcular_carencia, verificar_qualidade_segurado, calcular_tempo_contribuicao
from ..salario import calcular_salario_beneficio
from ..fator_previdenciario import calcular_coeficiente, rmi_com_coeficiente
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


class CalculadoraAposentadoriaIdade(CalculadoraBeneficio):

    @property
    def tipo_beneficio(self) -> TipoBeneficio:
        return TipoBeneficio.APOSENTADORIA_IDADE

    @property
    def nome(self) -> str:
        return "Aposentadoria por Idade (Regra Permanente EC 103/2019)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Art. 48; EC 103/2019 Art. 19"

    def verificar_requisitos(self, segurado: Segurado, der: date) -> ResultadoRequisitos:
        motivos = []

        # Idade mínima
        idade = segurado.idade_na(der)
        if segurado.sexo == Sexo.MASCULINO:
            idade_minima = IDADE_DEFINITIVA_HOMEM
        else:
            idade_minima = IDADE_DEFINITIVA_MULHER

        idade_ok = idade >= idade_minima

        # Carência
        meses_carencia = calcular_carencia(segurado.vinculos, der)
        carencia_ok = meses_carencia >= Carencia.APOSENTADORIA

        # TC
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)

        if not idade_ok:
            faltam = (idade_minima - idade) * Decimal("365.25")
            motivos.append(
                f"Idade insuficiente: {float(idade):.1f} anos "
                f"(exigido: {idade_minima} anos, faltam ~{int(faltam)} dias)"
            )
        if not carencia_ok:
            motivos.append(
                f"Carência insuficiente: {meses_carencia}/{Carencia.APOSENTADORIA} meses"
            )

        elegivel = idade_ok and carencia_ok

        return ResultadoRequisitos(
            elegivel=elegivel,
            carencia_ok=carencia_ok,
            carencia_meses_cumpridos=meses_carencia,
            carencia_meses_exigidos=Carencia.APOSENTADORIA,
            qualidade_segurado_ok=True,
            tempo_contribuicao=tc,
            faltam_dias=int(max(Decimal("0"), (idade_minima - idade) * Decimal("365.25"))),
            faltam_meses_carencia=max(0, Carencia.APOSENTADORIA - meses_carencia),
            motivos_inelegibilidade=motivos,
        )

    def calcular_rmi(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("CÁLCULO — APOSENTADORIA POR IDADE")

        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)

        mem.adicionar(f"TC = {tc.formatar()}", tc.anos_decimal)
        mem.adicionar(f"Idade na DER = {float(idade):.2f} anos")

        # SB
        resultado_sb = calcular_salario_beneficio(
            segurado.vinculos, der,
            usar_regra_ec103=True,
            aplicar_descarte=True,
            meses_carencia_exigidos=Carencia.APOSENTADORIA,
        )
        sb = resultado_sb["salario_beneficio"]
        mem.adicionar("Salário de Benefício (SB)", sb, formula=resultado_sb["regra_aplicada"])

        # Coeficiente
        coeficiente = calcular_coeficiente(tc.anos_decimal, segurado.sexo)
        mem.adicionar("Coeficiente", coeficiente,
                      formula="60% + 2% × anos TC acima do limiar (20H/15M)",
                      fundamentacao=DispositivoLegal(
                          "EC 103/2019", "Art. 26",
                          "Coeficiente da aposentadoria por idade/TC"
                      ))

        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi = rmi_com_coeficiente(sb, coeficiente, teto, piso)
        mem.adicionar("RMI final", rmi)

        return ResultadoRegra(
            nome_regra=self.nome,
            base_legal=self.base_legal,
            elegivel=True,
            rmi=rmi,
            rmi_teto=rmi,
            salario_beneficio=sb,
            coeficiente=coeficiente,
            tempo_contribuicao=tc,
            memoria=mem,
        )
