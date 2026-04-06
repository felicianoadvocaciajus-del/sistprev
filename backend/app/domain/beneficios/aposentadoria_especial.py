"""
Aposentadoria Especial — Espécie B46.
Lei 8.213/91 Arts. 57-58 e Decreto 3.048/99 Arts. 64-70.

Requisitos:
  - 15, 20 ou 25 anos de exposição a agentes nocivos (conforme categoria)
  - Carência: 180 contribuições mensais
  - Qualidade de segurado na DER

RMI = 100% do SB (sem coeficiente de redução).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .base import CalculadoraBeneficio
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra, ResultadoRequisitos, MemoriaCalculo, DispositivoLegal
from ..enums import TipoBeneficio, TipoAtividade
from ..constantes import Carencia, DatasCorte
from ..tempo import calcular_carencia, verificar_qualidade_segurado, calcular_tempo_contribuicao
from ..salario import calcular_salario_beneficio
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


# Mapeamento: tipo de atividade → anos exigidos
_ANOS_EXIGIDOS = {
    TipoAtividade.ESPECIAL_15: 15,
    TipoAtividade.ESPECIAL_20: 20,
    TipoAtividade.ESPECIAL_25: 25,
}


class CalculadoraAposentadoriaEspecial(CalculadoraBeneficio):

    def __init__(self, tipo_atividade: TipoAtividade = TipoAtividade.ESPECIAL_25):
        self._tipo = tipo_atividade
        self._anos_exigidos = _ANOS_EXIGIDOS.get(tipo_atividade, 25)

    @property
    def tipo_beneficio(self) -> TipoBeneficio:
        return TipoBeneficio.APOSENTADORIA_ESPECIAL

    @property
    def nome(self) -> str:
        return f"Aposentadoria Especial ({self._anos_exigidos} anos)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Arts. 57-58; Decreto 3.048/99 Arts. 64-70"

    def verificar_requisitos(self, segurado: Segurado, der: date) -> ResultadoRequisitos:
        motivos = []

        # Tempo especial efetivo (sem conversão — conta o tempo real da atividade)
        dias_especiais = self._contar_dias_especiais(segurado, der)
        dias_exigidos = self._anos_exigidos * 365

        tem_tempo_especial = dias_especiais >= dias_exigidos

        # Carência
        meses_carencia = calcular_carencia(segurado.vinculos, der)
        carencia_ok = meses_carencia >= Carencia.APOSENTADORIA

        # Qualidade de segurado
        tem_qualidade, _, justif = verificar_qualidade_segurado(segurado.vinculos, der)

        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)

        if not tem_tempo_especial:
            faltam = dias_exigidos - dias_especiais
            motivos.append(
                f"Tempo especial insuficiente: {dias_especiais // 365} anos "
                f"(exigido: {self._anos_exigidos}, faltam ~{faltam} dias)"
            )
        if not carencia_ok:
            motivos.append(f"Carência: {meses_carencia}/{Carencia.APOSENTADORIA} meses")
        if not tem_qualidade:
            motivos.append(justif)

        elegivel = tem_tempo_especial and carencia_ok and tem_qualidade

        return ResultadoRequisitos(
            elegivel=elegivel,
            carencia_ok=carencia_ok,
            carencia_meses_cumpridos=meses_carencia,
            carencia_meses_exigidos=Carencia.APOSENTADORIA,
            qualidade_segurado_ok=tem_qualidade,
            tempo_contribuicao=tc,
            faltam_dias=max(0, dias_exigidos - dias_especiais),
            faltam_meses_carencia=max(0, Carencia.APOSENTADORIA - meses_carencia),
            motivos_inelegibilidade=motivos,
        )

    def calcular_rmi(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("CÁLCULO — APOSENTADORIA ESPECIAL")

        dias_especiais = self._contar_dias_especiais(segurado, der)
        mem.adicionar(
            f"Tempo especial ({self._anos_exigidos} anos)",
            f"{dias_especiais // 365} anos e {(dias_especiais % 365) // 30} meses"
        )

        resultado_sb = calcular_salario_beneficio(
            segurado.vinculos, der,
            usar_regra_ec103=der >= DatasCorte.EC_103_2019,
            aplicar_descarte=True,
            meses_carencia_exigidos=Carencia.APOSENTADORIA,
        )
        sb = resultado_sb["salario_beneficio"]
        mem.adicionar("Salário de Benefício (SB)", sb, formula=resultado_sb["regra_aplicada"])

        # RMI = 100% do SB (aposentadoria especial — Art. 57 §1º)
        coeficiente = Decimal("1.0")
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi = max(piso, min(sb, teto))

        mem.adicionar("RMI = 100% do SB", rmi,
                      fundamentacao=DispositivoLegal(
                          "Lei 8.213/91", "Art. 57 §1º",
                          "Aposentadoria especial = 100% do salário de benefício"
                      ))

        return ResultadoRegra(
            nome_regra=self.nome,
            base_legal=self.base_legal,
            elegivel=True,
            rmi=rmi,
            rmi_teto=rmi,
            salario_beneficio=sb,
            coeficiente=coeficiente,
            memoria=mem,
        )

    def _contar_dias_especiais(self, segurado: Segurado, der: date) -> int:
        """Conta os dias de atividade especial do tipo exigido até a DER."""
        total = 0
        for v in segurado.vinculos:
            if v.tipo_atividade == self._tipo:
                fim = min(v.data_fim_efetiva, der)
                if v.data_inicio <= fim:
                    total += (fim - v.data_inicio).days + 1
        return total
