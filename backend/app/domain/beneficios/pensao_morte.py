"""
Pensão por Morte — Espécies B21 (urbana) e B22 (rural).
Lei 8.213/91 Arts. 74–79 (pré-EC103) e EC 103/2019 Art. 23 (pós).

Regra ANTES da EC 103/2019 (instituidor faleceu até 12/11/2019):
  Pensão = 100% da aposentadoria que recebia ou teria direito.

Regra APÓS EC 103/2019 (instituidor faleceu a partir de 13/11/2019):
  Base = RMI da aposentadoria por incapacidade permanente que teria direito.
  Pensão = 50% (cota familiar) + 10% × nº de dependentes.
  Máximo = 100% (para 5+ dependentes ou dependente inválido/deficiente grave).

Carência: sem carência (Art. 26 I Lei 8.213/91).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .base import CalculadoraBeneficio
from .invalidez import CalculadoraInvalidez
from ..models.segurado import Segurado, DadosPessoais, BeneficioAnterior
from ..models.resultado import ResultadoRegra, ResultadoRequisitos, MemoriaCalculo, DispositivoLegal
from ..enums import TipoBeneficio, Sexo
from ..constantes import (
    DatasCorte, Carencia,
    PENSAO_COTA_FAMILIAR, PENSAO_COTA_DEPENDENTE, PENSAO_MAXIMO,
)
from ..tempo import verificar_qualidade_segurado, calcular_tempo_contribuicao
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


class CalculadoraPensaoMorte(CalculadoraBeneficio):

    def __init__(
        self,
        num_dependentes: int = 1,
        tem_dependente_invalido: bool = False,
        data_obito: Optional[date] = None,
        rma_instituidor: Optional[Decimal] = None,
    ):
        """
        num_dependentes: número de dependentes habilitados (excluindo cônjuge/companheiro).
        tem_dependente_invalido: True se algum dependente é inválido ou deficiente grave.
        data_obito: data do falecimento do instituidor (determina regra pré/pós EC103).
        rma_instituidor: Renda Mensal Atual da aposentadoria que o instituidor recebia.
                         Se None, calcula o que teria direito (invalidez).
        """
        self._num_dependentes = num_dependentes
        self._tem_invalido = tem_dependente_invalido
        self._data_obito = data_obito
        self._rma_instituidor = rma_instituidor

    @property
    def tipo_beneficio(self) -> TipoBeneficio:
        return TipoBeneficio.PENSAO_MORTE_URBANA

    @property
    def nome(self) -> str:
        return "Pensão por Morte"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Arts. 74-79; EC 103/2019 Art. 23"

    def verificar_requisitos(self, segurado: Segurado, der: date) -> ResultadoRequisitos:
        from ..models.periodo import TempoContribuicao
        # Pensão por morte não tem carência
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        tem_qualidade, _, justif = verificar_qualidade_segurado(segurado.vinculos, der)

        motivos = []
        if not tem_qualidade:
            motivos.append(f"Segurado sem qualidade de segurado na DER: {justif}")

        return ResultadoRequisitos(
            elegivel=tem_qualidade,
            carencia_ok=True,
            carencia_meses_cumpridos=0,
            carencia_meses_exigidos=0,
            qualidade_segurado_ok=tem_qualidade,
            tempo_contribuicao=tc,
            motivos_inelegibilidade=motivos,
        )

    def calcular_rmi(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("CÁLCULO — PENSÃO POR MORTE")

        data_obito = self._data_obito or der
        pre_ec103 = data_obito < DatasCorte.EC_103_2019

        # ── BASE DE CÁLCULO ────────────────────────────────────────────────────
        if self._rma_instituidor and self._rma_instituidor > Decimal("0"):
            base = self._rma_instituidor
            mem.adicionar("Base: RMA da aposentadoria recebida", base)
        else:
            # Calcular a aposentadoria por invalidez que teria direito
            calc_invalidez = CalculadoraInvalidez(acidentaria=False)
            resultado_inv = calc_invalidez.calcular_rmi(segurado, data_obito)
            base = resultado_inv.rmi_teto
            mem.adicionar("Base: aposentadoria por invalidez que teria direito", base,
                          formula="Calculada conforme Arts. 42-44 Lei 8.213/91")

        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)

        # ── REGRA PRÉ-EC 103/2019 ──────────────────────────────────────────────
        if pre_ec103:
            rmi = min(base, teto)
            rmi = max(rmi, piso)
            mem.adicionar("Regra pré-EC 103/2019: 100% da RMI do instituidor", rmi,
                          fundamentacao=DispositivoLegal(
                              "Lei 8.213/91", "Art. 75",
                              "Pensão por morte = 100% da aposentadoria (regra anterior à EC 103/2019)"
                          ))
            return ResultadoRegra(
                nome_regra="Pensão por Morte (pré-EC 103/2019)",
                base_legal="Lei 8.213/91 Art. 75",
                elegivel=True,
                rmi=rmi,
                rmi_teto=rmi,
                salario_beneficio=base,
                coeficiente=Decimal("1.0"),
                memoria=mem,
            )

        # ── REGRA PÓS-EC 103/2019 ──────────────────────────────────────────────
        if self._tem_invalido:
            coeficiente = PENSAO_MAXIMO  # 100% quando há inválido
            mem.adicionar("Dependente inválido/deficiente grave → coeficiente 100%",
                          coeficiente,
                          fundamentacao=DispositivoLegal(
                              "EC 103/2019", "Art. 23 §2º",
                              "100% quando há dependente inválido ou com deficiência"
                          ))
        else:
            cotas = min(
                PENSAO_COTA_FAMILIAR + PENSAO_COTA_DEPENDENTE * Decimal(str(self._num_dependentes)),
                PENSAO_MAXIMO,
            )
            coeficiente = cotas
            mem.adicionar(f"Cotas: 50% + 10% × {self._num_dependentes} dependente(s)", coeficiente,
                          formula="50% (familiar) + 10% × nº dependentes",
                          fundamentacao=DispositivoLegal(
                              "EC 103/2019", "Art. 23",
                              "Pensão = 50% + 10% por dependente, máximo 100%"
                          ))

        rmi = (base * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rmi = max(piso, min(rmi, teto))
        mem.adicionar("RMI final", rmi)

        return ResultadoRegra(
            nome_regra="Pensão por Morte (pós-EC 103/2019)",
            base_legal="EC 103/2019 Art. 23",
            elegivel=True,
            rmi=rmi,
            rmi_teto=rmi,
            salario_beneficio=base,
            coeficiente=coeficiente,
            memoria=mem,
        )
