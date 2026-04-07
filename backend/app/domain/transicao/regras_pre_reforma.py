"""
Regras de aposentadoria PRE-REFORMA (anteriores a 13/11/2019).

Aplicam-se EXCLUSIVAMENTE quando DER < 13/11/2019.
Principio: tempus regit actum — a lei vigente na data do fato rege o ato.

Regra 1 — TC Puro + Fator Previdenciario (obrigatorio)
  Lei 8.213/91 Art. 52 + Lei 9.876/99 Art. 29.
  Requisitos: 35H/30M de TC + 180 meses de carencia. Sem idade minima.
  SB = media dos 80% maiores SC desde Jul/1994.
  RMI = SB x FP.

Regra 2 — Regra 85/95 Progressiva (Art. 29-C Lei 8.213/91)
  Incluida pela Lei 13.183/2015 (vigente a partir de 18/06/2015).
  Se pontos (idade + TC) >= 85M/95H (progressiva), AFASTA o FP.
  SB = media dos 80% maiores SC desde Jul/1994.
  RMI = 100% do SB (sem FP).
  Tabela progressiva: 85/95 (2015-2018), 86/96 (2019), etc.

Regra 3 — Aposentadoria por Idade Pre-Reforma
  Lei 8.213/91 Art. 48 (redacao anterior a EC 103).
  Requisitos: 65H/60M de idade + 180 meses de carencia.
  SB = media dos 80% maiores SC desde Jul/1994.
  RMI = SB x (70% + 1% por grupo de 12 contribuicoes, max 100%).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .base import RegraTransicao
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra, MemoriaCalculo, DispositivoLegal
from ..enums import Sexo
from ..constantes import (
    DatasCorte,
    TC_MINIMO_HOMEM_PRE_EC103, TC_MINIMO_MULHER_PRE_EC103,
    Carencia,
)
from ..tempo import calcular_tempo_contribuicao, calcular_carencia
from ..salario import calcular_salario_beneficio
from ..fator_previdenciario import (
    calcular_fator_previdenciario, rmi_com_fator,
)
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES PRE-REFORMA
# ──────────────────────────────────────────────────────────────────────────────

# Tabela de pontos 85/95 progressiva (Lei 13.183/2015, Art. 29-C §1)
# A partir de 31/12/2018: +1 ponto a cada ano
PONTOS_85_95 = {
    # ano: (homem, mulher)
    2015: (95, 85),
    2016: (95, 85),
    2017: (95, 85),
    2018: (95, 85),
    # A partir de 2019 seria 96/86, mas a EC 103 entrou em 13/11/2019
    # e substituiu esta regra pelas regras de transicao.
    # Para DER entre 01/01/2019 e 12/11/2019, a regra 85/95 ainda valia
    # com a progressao que seria 96/86.
    2019: (96, 86),
}

# Data de inicio de vigencia da regra 85/95
DATA_INICIO_85_95 = date(2015, 6, 18)  # Lei 13.183/2015 (MP 676/2015)


def _tc_minimo_pre(sexo: Sexo) -> Decimal:
    return TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103


def _pontos_85_95(sexo: Sexo, ano: int) -> Decimal:
    """Pontuacao exigida na regra 85/95 para um dado ano."""
    if ano < 2015:
        # Antes da lei, nao existia esta regra
        return Decimal("999")  # Impossivel atingir
    ano_consulta = min(ano, 2019)
    pts = PONTOS_85_95.get(ano_consulta, PONTOS_85_95[2019])
    if sexo == Sexo.MASCULINO:
        return Decimal(str(pts[0]))
    return Decimal(str(pts[1]))


def _calcular_sb_pre_reforma(segurado: Segurado, der: date, mem: MemoriaCalculo):
    """
    Calcula SB com regra PRE-EC103: media dos 80% maiores SC desde Jul/1994.
    Lei 9.876/99 Art. 29, II + divisor minimo (Art. 29 §§5-6).
    """
    resultado_sb = calcular_salario_beneficio(
        segurado.vinculos, der,
        usar_regra_ec103=False,  # ← CRUCIAL: 80% maiores, NAO 100%
        aplicar_descarte=False,   # Descarte e da EC 103, nao se aplica
        meses_carencia_exigidos=Carencia.APOSENTADORIA,
    )
    sb = resultado_sb["salario_beneficio"]
    mem.adicionar(
        "SB (80% maiores SC)", sb,
        formula=resultado_sb["regra_aplicada"],
        fundamentacao=DispositivoLegal(
            norma="Lei 9.876/99",
            artigo="Art. 29, II",
            descricao="Media aritmetica simples dos maiores salarios de contribuicao "
                      "correspondentes a 80% de todo o periodo contributivo"
        ),
    )
    return sb, resultado_sb


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 1 — TC PURO + FATOR PREVIDENCIARIO (Lei 8.213/91 + Lei 9.876/99)
# ──────────────────────────────────────────────────────────────────────────────
class RegraTCComFator(RegraTransicao):
    """
    Aposentadoria por Tempo de Contribuicao com Fator Previdenciario obrigatorio.
    Vigente para DER de 29/11/1999 a 12/11/2019.
    Requisitos: 35H/30M de TC + 180 meses de carencia.
    """
    @property
    def nome(self) -> str:
        return "Aposentadoria por TC + Fator Previdenciario (Lei 8.213/91)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Art. 52; Lei 9.876/99 Art. 29"

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc_min = _tc_minimo_pre(segurado.sexo)
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        return tc.anos_decimal >= tc_min and carencia >= Carencia.APOSENTADORIA

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("APOSENTADORIA POR TC + FATOR PREVIDENCIARIO")

        # Trava temporal: so se aplica para DER < 13/11/2019
        if der >= DatasCorte.EC_103_2019:
            mem.adicionar(
                "REGRA NAO APLICAVEL",
                formula=f"DER ({der}) >= 13/11/2019. Esta regra so se aplica antes da EC 103/2019."
            )
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                avisos=["Regra nao aplicavel: DER posterior a EC 103/2019"],
            )

        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc_min = _tc_minimo_pre(segurado.sexo)
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        idade = segurado.idade_na(der)

        mem.adicionar(f"TC: {tc.formatar()} ({float(tc.anos_decimal):.2f} anos)")
        mem.adicionar(f"TC minimo exigido: {tc_min} anos")
        mem.adicionar(f"Carencia: {carencia} meses (exigido: {Carencia.APOSENTADORIA})")
        mem.adicionar(f"Idade na DER: {float(idade):.1f} anos")

        elegivel = tc.anos_decimal >= tc_min and carencia >= Carencia.APOSENTADORIA

        if not elegivel:
            faltam_tc = max(Decimal("0"), tc_min - tc.anos_decimal)
            faltam_car = max(0, Carencia.APOSENTADORIA - carencia)
            mem.adicionar(f"NAO ELEGIVEL — faltam {float(faltam_tc):.2f} anos de TC "
                          f"e {faltam_car} meses de carencia")
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                faltam_dias=int(max(faltam_tc * Decimal("365.25"),
                                    Decimal(str(faltam_car * 30)))),
            )

        # SB com regra pre-reforma (80% maiores)
        sb, _ = _calcular_sb_pre_reforma(segurado, der, mem)

        # Fator Previdenciario
        fp = calcular_fator_previdenciario(tc.anos_decimal, idade, der)
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi_bruta = rmi_com_fator(sb, fp, teto)
        rmi = max(piso, rmi_bruta)

        mem.adicionar(f"Fator Previdenciario: {float(fp):.4f}",
                      formula="f = (Tc x 0.31 / Es) x [1 + (Id + Tc x 0.31) / 100]",
                      fundamentacao=DispositivoLegal(
                          norma="Lei 9.876/99", artigo="Art. 29-B",
                          descricao="Fator Previdenciario — obrigatorio nesta regra"
                      ))
        mem.adicionar(f"RMI = SB x FP = {float(sb):.2f} x {float(fp):.4f} = {float(rmi):.2f}")

        return ResultadoRegra(
            nome_regra=self.nome, base_legal=self.base_legal,
            elegivel=True, rmi=rmi, rmi_teto=rmi,
            salario_beneficio=sb, fator_previdenciario=fp,
            tempo_contribuicao=tc, memoria=mem,
        )


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 2 — REGRA 85/95 (Art. 29-C Lei 8.213/91) — AFASTA O FP
# ──────────────────────────────────────────────────────────────────────────────
class Regra85_95(RegraTransicao):
    """
    Regra de pontos que AFASTA o Fator Previdenciario.
    Lei 13.183/2015 (incluiu Art. 29-C na Lei 8.213/91).
    Vigente de 18/06/2015 a 12/11/2019.

    Se pontos (idade + TC) >= limiar progressivo, RMI = 100% do SB.
    Progressao: 85/95 (2015-2018), 86/96 (2019).
    """
    @property
    def nome(self) -> str:
        return "Regra 85/95 — Afasta FP (Art. 29-C Lei 8.213/91)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Art. 29-C (incluido pela Lei 13.183/2015)"

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        # Trava temporal
        if der < DATA_INICIO_85_95 or der >= DatasCorte.EC_103_2019:
            return False
        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc_min = _tc_minimo_pre(segurado.sexo)
        if tc.anos_decimal < tc_min:
            return False
        idade = segurado.idade_na(der)
        pontos = tc.anos_decimal + idade
        pontos_exigidos = _pontos_85_95(segurado.sexo, der.year)
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        return pontos >= pontos_exigidos and carencia >= Carencia.APOSENTADORIA

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 85/95 — AFASTA FATOR PREVIDENCIARIO")

        # Trava temporal
        if der < DATA_INICIO_85_95:
            mem.adicionar(
                "REGRA NAO APLICAVEL",
                formula=f"DER ({der}) anterior a 18/06/2015. "
                        "A regra 85/95 so existe a partir da Lei 13.183/2015."
            )
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                avisos=["Regra nao vigente na DER informada"],
            )

        if der >= DatasCorte.EC_103_2019:
            mem.adicionar(
                "REGRA NAO APLICAVEL",
                formula=f"DER ({der}) >= 13/11/2019. "
                        "A regra 85/95 foi substituida pelas regras de transicao da EC 103/2019."
            )
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                avisos=["Regra substituida pela EC 103/2019"],
            )

        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc_min = _tc_minimo_pre(segurado.sexo)
        idade = segurado.idade_na(der)
        pontos = tc.anos_decimal + idade
        pontos_exigidos = _pontos_85_95(segurado.sexo, der.year)
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )

        mem.adicionar(f"TC: {tc.formatar()} ({float(tc.anos_decimal):.2f} anos)")
        mem.adicionar(f"TC minimo: {tc_min} anos")
        mem.adicionar(f"Idade: {float(idade):.1f} anos")
        mem.adicionar(f"Pontos: {float(pontos):.2f} (exigido: {pontos_exigidos})")
        mem.adicionar(f"Carencia: {carencia} meses (exigido: {Carencia.APOSENTADORIA})")

        elegivel = (
            tc.anos_decimal >= tc_min
            and pontos >= pontos_exigidos
            and carencia >= Carencia.APOSENTADORIA
        )

        if not elegivel:
            faltam_pts = max(Decimal("0"), pontos_exigidos - pontos)
            faltam_tc = max(Decimal("0"), tc_min - tc.anos_decimal)
            mem.adicionar(f"NAO ELEGIVEL — faltam {float(faltam_pts):.2f} pontos "
                          f"e {float(faltam_tc):.2f} anos de TC")
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                faltam_dias=int(max(faltam_pts, faltam_tc) * Decimal("365.25")),
            )

        # SB com regra pre-reforma (80% maiores)
        sb, _ = _calcular_sb_pre_reforma(segurado, der, mem)

        # RMI = 100% do SB (o FP e AFASTADO pela regra 85/95)
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi = max(piso, min(sb, teto))

        mem.adicionar(
            f"RMI = 100% do SB = R$ {float(rmi):.2f}",
            formula="Art. 29-C: Fator Previdenciario AFASTADO quando pontos >= 85/95",
            fundamentacao=DispositivoLegal(
                norma="Lei 8.213/91", artigo="Art. 29-C",
                descricao="O segurado que preencher o requisito de pontos tem direito "
                          "a aposentadoria por TC sem incidencia do FP"
            ),
        )

        return ResultadoRegra(
            nome_regra=self.nome, base_legal=self.base_legal,
            elegivel=True, rmi=rmi, rmi_teto=rmi,
            salario_beneficio=sb, coeficiente=Decimal("1.0"),
            tempo_contribuicao=tc, memoria=mem,
        )


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 3 — APOSENTADORIA POR IDADE PRE-REFORMA
# ──────────────────────────────────────────────────────────────────────────────
class RegraIdadePreReforma(RegraTransicao):
    """
    Aposentadoria por Idade — Lei 8.213/91 Art. 48 (redacao pre-EC 103).
    Requisitos: 65H/60M de idade + 180 meses de carencia.
    RMI = SB x (70% + 1% por grupo de 12 contribuicoes), max 100%.
    """
    @property
    def nome(self) -> str:
        return "Aposentadoria por Idade (Lei 8.213/91 Art. 48)"

    @property
    def base_legal(self) -> str:
        return "Lei 8.213/91 Art. 48 e Art. 50"

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        if der >= DatasCorte.EC_103_2019:
            return False
        idade = segurado.idade_na(der)
        idade_min = Decimal("65") if segurado.sexo == Sexo.MASCULINO else Decimal("60")
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        return idade >= idade_min and carencia >= Carencia.APOSENTADORIA

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("APOSENTADORIA POR IDADE (PRE-REFORMA)")

        if der >= DatasCorte.EC_103_2019:
            mem.adicionar(
                "REGRA NAO APLICAVEL",
                formula=f"DER ({der}) >= 13/11/2019. Use a regra permanente da EC 103."
            )
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
            )

        idade = segurado.idade_na(der)
        idade_min = Decimal("65") if segurado.sexo == Sexo.MASCULINO else Decimal("60")
        carencia = calcular_carencia(
            segurado.vinculos, der,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )

        mem.adicionar(f"Idade: {float(idade):.1f} anos (minimo: {idade_min})")
        mem.adicionar(f"Carencia: {carencia} meses (exigido: {Carencia.APOSENTADORIA})")

        elegivel = idade >= idade_min and carencia >= Carencia.APOSENTADORIA

        if not elegivel:
            faltam_id = max(Decimal("0"), (idade_min - idade))
            faltam_car = max(0, Carencia.APOSENTADORIA - carencia)
            mem.adicionar(f"NAO ELEGIVEL — faltam {float(faltam_id):.1f} anos de idade "
                          f"e {faltam_car} meses de carencia")
            return ResultadoRegra(
                nome_regra=self.nome, base_legal=self.base_legal,
                elegivel=False, memoria=mem,
                faltam_dias=int(max(faltam_id * Decimal("365.25"),
                                    Decimal(str(faltam_car * 30)))),
            )

        # SB com regra pre-reforma (80% maiores)
        sb, _ = _calcular_sb_pre_reforma(segurado, der, mem)

        # Coeficiente: 70% + 1% por grupo de 12 contribuicoes (Art. 50)
        grupos_12 = carencia // 12
        coef_pct = min(Decimal("70") + Decimal(str(grupos_12)), Decimal("100"))
        coeficiente = coef_pct / Decimal("100")

        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi = max(piso, min(sb * coeficiente, teto))
        rmi = rmi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        mem.adicionar(
            f"Coeficiente: {float(coef_pct):.0f}% (70% + 1% x {grupos_12} grupos de 12 contrib)",
            fundamentacao=DispositivoLegal(
                norma="Lei 8.213/91", artigo="Art. 50",
                descricao="A aposentadoria por idade consistira numa renda mensal de "
                          "70% do SB, mais 1% por grupo de 12 contribuicoes mensais"
            ),
        )
        mem.adicionar(f"RMI = SB x {float(coeficiente):.4f} = R$ {float(rmi):.2f}")

        return ResultadoRegra(
            nome_regra=self.nome, base_legal=self.base_legal,
            elegivel=True, rmi=rmi, rmi_teto=rmi,
            salario_beneficio=sb, coeficiente=coeficiente,
            tempo_contribuicao=tc, memoria=mem,
        )
