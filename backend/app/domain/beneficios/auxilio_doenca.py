"""
Auxílio por Incapacidade Temporária (antigo Auxílio-Doença).
Espécies B31 (previdenciário) e B91 (acidentário).

Lei 8.213/91 Arts. 59–63 e Decreto 3.048/99 Arts. 71–80.

RMI = 91% do SB
Limitador: RMI não pode superar a média dos últimos 12 SC (Art. 29 §10).
Carência: 12 contribuições mensais (dispensada em acidente ou doença do Art. 151).
Período de espera do empregado CLT: 15 dias (empresa paga); INSS a partir do 16º.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .base import CalculadoraBeneficio
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra, ResultadoRequisitos, MemoriaCalculo, DispositivoLegal
from ..enums import TipoBeneficio, Sexo
from ..constantes import Carencia, DatasCorte
from ..tempo import calcular_carencia, verificar_qualidade_segurado
from ..salario import calcular_salario_beneficio
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


_COEF_AUXILIO = Decimal("0.91")


class CalculadoraAuxilioDoenca(CalculadoraBeneficio):

    def __init__(self, acidentario: bool = False):
        self._acidentario = acidentario

    @property
    def tipo_beneficio(self) -> TipoBeneficio:
        return TipoBeneficio.AUXILIO_DOENCA_ACID if self._acidentario else TipoBeneficio.AUXILIO_DOENCA_PREV

    @property
    def nome(self) -> str:
        return "Auxílio por Incapacidade Temporária (Acidentário)" if self._acidentario \
            else "Auxílio por Incapacidade Temporária (Previdenciário)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Arts. 59-63; Decreto 3.048/99 Arts. 71-80"

    def verificar_requisitos(self, segurado: Segurado, der: date) -> ResultadoRequisitos:
        from ..models.periodo import TempoContribuicao
        from ..tempo import calcular_tempo_contribuicao

        mem = MemoriaCalculo()
        motivos = []

        # Qualidade de segurado
        tem_qualidade, _, justif_qualidade = verificar_qualidade_segurado(
            segurado.vinculos, der
        )

        # Carência
        meses_carencia = calcular_carencia(segurado.vinculos, der)
        carencia_ok = self._acidentario or meses_carencia >= Carencia.AUXILIO_DOENCA

        # Tempo de contribuição (informativo)
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)

        if not tem_qualidade:
            motivos.append(f"Sem qualidade de segurado na DER: {justif_qualidade}")
        if not carencia_ok:
            motivos.append(
                f"Carência insuficiente: {meses_carencia} meses (exigido: {Carencia.AUXILIO_DOENCA})"
            )

        elegivel = tem_qualidade and carencia_ok

        return ResultadoRequisitos(
            elegivel=elegivel,
            carencia_ok=carencia_ok,
            carencia_meses_cumpridos=meses_carencia,
            carencia_meses_exigidos=0 if self._acidentario else Carencia.AUXILIO_DOENCA,
            qualidade_segurado_ok=tem_qualidade,
            tempo_contribuicao=tc,
            faltam_meses_carencia=max(0, Carencia.AUXILIO_DOENCA - meses_carencia),
            motivos_inelegibilidade=motivos,
        )

    def calcular_rmi(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("CÁLCULO — AUXÍLIO POR INCAPACIDADE TEMPORÁRIA")

        # Determinar regra do PBC (pós ou pré EC103)
        usar_ec103 = der >= DatasCorte.EC_103_2019

        # Calcular SB
        resultado_sb = calcular_salario_beneficio(
            segurado.vinculos, der,
            usar_regra_ec103=usar_ec103,
            aplicar_descarte=usar_ec103,
            meses_carencia_exigidos=Carencia.AUXILIO_DOENCA,
        )
        sb = resultado_sb["salario_beneficio"]
        mem.adicionar("Salário de Benefício (SB)", sb,
                      formula=resultado_sb["regra_aplicada"])

        # RMI = 91% do SB
        rmi_bruta = (sb * _COEF_AUXILIO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        mem.adicionar("RMI bruta (91% do SB)", rmi_bruta,
                      formula="RMI = SB × 91%",
                      fundamentacao=DispositivoLegal(
                          "Lei 8.213/91", "Art. 61",
                          "RMI do auxílio por incapacidade = 91% do salário de benefício"
                      ))

        # Limitador: não pode superar a média dos últimos 12 SC (Art. 29 §10)
        media_12 = self._media_ultimos_12_sc(segurado, der)
        if media_12 > Decimal("0") and rmi_bruta > media_12:
            rmi_bruta = media_12
            mem.adicionar("Limitador Art. 29 §10 aplicado", media_12,
                          formula="RMI limitada à média dos últimos 12 SC",
                          fundamentacao=DispositivoLegal(
                              "Lei 8.213/91", "Art. 29 §10",
                              "RMI não pode superar a média dos últimos 12 salários de contribuição"
                          ))

        # Aplicar piso e teto
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi_final = max(piso, min(rmi_bruta, teto))
        mem.adicionar("RMI final (após piso/teto)", rmi_final)

        return ResultadoRegra(
            nome_regra=self.nome,
            base_legal=self.base_legal,
            elegivel=True,
            rmi=rmi_final,
            rmi_teto=rmi_final,
            salario_beneficio=sb,
            coeficiente=_COEF_AUXILIO,
            memoria=mem,
        )

    def _media_ultimos_12_sc(self, segurado: Segurado, der: date) -> Decimal:
        """Média dos últimos 12 salários de contribuição antes da DER (Art. 29 §10)."""
        from ..models.contribuicao import Competencia
        from ..indices import teto_em

        todos = []
        for v in segurado.vinculos:
            for c in v.contribuicoes:
                if c.competencia < date(der.year, der.month, 1) and c.valida_tc:
                    teto = teto_em(c.competencia.year, c.competencia.month)
                    todos.append(min(c.salario_contribuicao, teto))

        if not todos:
            return Decimal("0")

        ultimos_12 = sorted(todos, reverse=True)[:12]
        return (sum(ultimos_12) / Decimal(str(len(ultimos_12)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
