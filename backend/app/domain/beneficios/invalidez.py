"""
Aposentadoria por Incapacidade Permanente (antigas: por Invalidez).
Espécies B32 (previdenciária) e B92 (acidentária).

Lei 8.213/91 Arts. 42–47 e Decreto 3.048/99 Arts. 43–50.

RMI (B32 previdenciária) = SB × coeficiente (60% + 2%/ano excedente, pós-EC103)
                         = 100% do SB se acidentária (B92)
Acréscimo de 25% quando o segurado necessitar de assistência permanente (Art. 45).
Carência: 12 contribuições (dispensada em acidente de qualquer natureza ou doença do Art. 151).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .base import CalculadoraBeneficio
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra, ResultadoRequisitos, MemoriaCalculo, DispositivoLegal
from ..enums import TipoBeneficio
from ..constantes import Carencia, DatasCorte, COEFICIENTE_INVALIDEZ_ACID, ACRESCIMO_GRANDE_INVALIDO
from ..tempo import calcular_carencia, verificar_qualidade_segurado, calcular_tempo_contribuicao
from ..salario import calcular_salario_beneficio
from ..fator_previdenciario import calcular_coeficiente
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


class CalculadoraInvalidez(CalculadoraBeneficio):

    def __init__(self, acidentaria: bool = False, grande_invalido: bool = False):
        self._acidentaria = acidentaria
        self._grande_invalido = grande_invalido

    @property
    def tipo_beneficio(self) -> TipoBeneficio:
        return TipoBeneficio.APOSENTADORIA_INVALIDEZ_ACID if self._acidentaria \
            else TipoBeneficio.APOSENTADORIA_INVALIDEZ_PREV

    @property
    def nome(self) -> str:
        base = "Aposentadoria por Incapacidade Permanente"
        tipo = " (Acidentária)" if self._acidentaria else " (Previdenciária)"
        gi = " + Acréscimo 25% Grande Inválido" if self._grande_invalido else ""
        return base + tipo + gi

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Arts. 42-47; Decreto 3.048/99 Arts. 43-50"

    def verificar_requisitos(self, segurado: Segurado, der: date) -> ResultadoRequisitos:
        motivos = []

        tem_qualidade, _, justif = verificar_qualidade_segurado(segurado.vinculos, der)
        meses_carencia = calcular_carencia(segurado.vinculos, der)
        carencia_ok = self._acidentaria or meses_carencia >= Carencia.APOSENTADORIA_INVALIDEZ
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)

        if not tem_qualidade:
            motivos.append(f"Sem qualidade de segurado: {justif}")
        if not carencia_ok:
            motivos.append(f"Carência: {meses_carencia}/{Carencia.APOSENTADORIA_INVALIDEZ} meses")

        return ResultadoRequisitos(
            elegivel=tem_qualidade and carencia_ok,
            carencia_ok=carencia_ok,
            carencia_meses_cumpridos=meses_carencia,
            carencia_meses_exigidos=0 if self._acidentaria else Carencia.APOSENTADORIA_INVALIDEZ,
            qualidade_segurado_ok=tem_qualidade,
            tempo_contribuicao=tc,
            faltam_meses_carencia=max(0, Carencia.APOSENTADORIA_INVALIDEZ - meses_carencia),
            motivos_inelegibilidade=motivos,
        )

    def calcular_rmi(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("CÁLCULO — APOSENTADORIA POR INCAPACIDADE PERMANENTE")

        usar_ec103 = der >= DatasCorte.EC_103_2019
        resultado_sb = calcular_salario_beneficio(
            segurado.vinculos, der,
            usar_regra_ec103=usar_ec103,
            aplicar_descarte=usar_ec103,
            meses_carencia_exigidos=Carencia.APOSENTADORIA_INVALIDEZ,
        )
        sb = resultado_sb["salario_beneficio"]
        mem.adicionar("Salário de Benefício (SB)", sb, formula=resultado_sb["regra_aplicada"])

        if self._acidentaria:
            coeficiente = COEFICIENTE_INVALIDEZ_ACID  # 100%
            rmi = sb
            mem.adicionar("Coeficiente (acidentária)", coeficiente,
                          formula="100% do SB — acidente de trabalho",
                          fundamentacao=DispositivoLegal(
                              "Lei 8.213/91", "Art. 44 §1º",
                              "Aposentadoria acidentária = 100% do salário de benefício"
                          ))
        else:
            # Pós-EC103: aplica coeficiente 60%+2%/ano
            tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
            coeficiente = calcular_coeficiente(tc.anos_decimal, segurado.sexo)
            rmi = (sb * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            mem.adicionar(f"TC = {tc.formatar()}", tc.anos_decimal)
            mem.adicionar("Coeficiente (previdenciária)", coeficiente,
                          formula="60% + 2% × anos excedentes ao limiar",
                          fundamentacao=DispositivoLegal(
                              "EC 103/2019", "Art. 26",
                              "Coeficiente mínimo de 60% + 2% por ano acima do mínimo"
                          ))

        # Acréscimo de 25% — grande inválido (Art. 45 Lei 8.213/91)
        if self._grande_invalido:
            rmi = rmi * (Decimal("1") + ACRESCIMO_GRANDE_INVALIDO)
            rmi = rmi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            mem.adicionar("Acréscimo 25% (grande inválido)", rmi,
                          formula="RMI × 1,25 — pode ultrapassar o teto",
                          fundamentacao=DispositivoLegal(
                              "Lei 8.213/91", "Art. 45",
                              "Acréscimo de 25% quando necessária assistência permanente"
                          ))
            # Grande inválido pode ultrapassar o teto — só aplica piso
            piso = salario_minimo_na_data(der)
            rmi_final = max(piso, rmi)
        else:
            rmi_final = self._aplicar_limites(rmi, der)

        mem.adicionar("RMI final", rmi_final)

        return ResultadoRegra(
            nome_regra=self.nome,
            base_legal=self.base_legal,
            elegivel=True,
            rmi=rmi_final,
            rmi_teto=rmi_final,
            salario_beneficio=sb,
            coeficiente=coeficiente,
            memoria=mem,
        )
