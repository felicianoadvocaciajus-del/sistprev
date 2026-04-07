"""
Cinco regras de transição da EC 103/2019 para Aposentadoria por Tempo de Contribuição.

Regra 1 — Art. 15 — Sistema de Pontos Progressivos
  Pontos = Idade + TC. Escala: 96/86 (2019) → 105/100 (2033+).
  RMI = SB × coeficiente (60% + 2%/ano excedente). Sem FP.

Regra 2 — Art. 16 — Idade Mínima Progressiva
  Idade cresce até 65H/62M (2027/2031). TC mínimo: 35H/30M.
  RMI = SB × coeficiente. Sem FP.

Regra 3 — Art. 17 — Pedágio 50% + Fator Previdenciário
  Elegível: quem tinha ≥ 33H/28M anos de TC em 13/11/2019.
  Pedágio = 50% do que faltava. RMI = SB × FP (obrigatório).

Regra 4 — Art. 20 — Pedágio 100% + Idade Mínima
  Pedágio = 100% do que faltava. Idade: 60H/57M. RMI = 100% do SB.

Regra 5 — Direito Adquirido (pré-EC103)
  Completou 35H/30M antes de 13/11/2019. RMI = SB × FP.
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
    DatasCorte, PONTOS_EC103, PONTOS_EC103_TETO_HOMEM, PONTOS_EC103_TETO_MULHER,
    TC_MINIMO_HOMEM_PRE_EC103, TC_MINIMO_MULHER_PRE_EC103,
)
from ..tempo import calcular_tempo_contribuicao
from ..salario import calcular_salario_beneficio
from ..fator_previdenciario import (
    calcular_fator_previdenciario, calcular_coeficiente,
    rmi_com_fator, rmi_com_coeficiente,
)
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data
from ..constantes import Carencia


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS COMPARTILHADOS
# ──────────────────────────────────────────────────────────────────────────────

def _tc_minimo(sexo: Sexo) -> Decimal:
    return TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103


def _tc_em_13nov2019(segurado: Segurado) -> Decimal:
    """TC (em anos) na data de promulgação da EC 103/2019."""
    tc = calcular_tempo_contribuicao(
        segurado.vinculos, DatasCorte.EC_103_2019, segurado.sexo
    )
    return tc.anos_decimal


def _pontos_exigidos(sexo: Sexo, ano: int) -> Decimal:
    """Pontuação exigida no sistema de pontos para um dado ano."""
    ano_consulta = min(ano, 2033)
    if ano_consulta < 2019:
        ano_consulta = 2019
    pts = PONTOS_EC103.get(ano_consulta, PONTOS_EC103[2033])
    if sexo == Sexo.MASCULINO:
        return Decimal(str(pts[0]))
    return Decimal(str(pts[1]))


def _calcular_sb_e_rmi_coef(segurado: Segurado, der: date, mem: MemoriaCalculo):
    """Calcula SB e RMI com coeficiente (padrão EC 103 sem FP)."""
    resultado_sb = calcular_salario_beneficio(
        segurado.vinculos, der, usar_regra_ec103=True,
        aplicar_descarte=True, meses_carencia_exigidos=Carencia.APOSENTADORIA,
    )
    sb = resultado_sb["salario_beneficio"]
    tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
    coeficiente = calcular_coeficiente(tc.anos_decimal, segurado.sexo)
    teto = teto_na_data(der)
    piso = salario_minimo_na_data(der)
    rmi = rmi_com_coeficiente(sb, coeficiente, teto, piso)

    mem.adicionar("SB", sb, formula=resultado_sb["regra_aplicada"])
    mem.adicionar(f"TC = {tc.formatar()}", tc.anos_decimal)
    mem.adicionar("Coeficiente", coeficiente, formula="60% + 2%/ano excedente")
    mem.adicionar("RMI", rmi)
    return sb, coeficiente, rmi, tc


def _calcular_sb_e_rmi_fp(segurado: Segurado, der: date, mem: MemoriaCalculo):
    """Calcula SB e RMI com Fator Previdenciário (obrigatório)."""
    resultado_sb = calcular_salario_beneficio(
        segurado.vinculos, der, usar_regra_ec103=True,
        aplicar_descarte=True, meses_carencia_exigidos=Carencia.APOSENTADORIA,
    )
    sb = resultado_sb["salario_beneficio"]
    tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
    idade = segurado.idade_na(der)
    fp = calcular_fator_previdenciario(tc.anos_decimal, idade, der)
    teto = teto_na_data(der)
    piso = salario_minimo_na_data(der)
    rmi = max(piso, rmi_com_fator(sb, fp, teto))

    mem.adicionar("SB", sb)
    mem.adicionar(f"TC = {tc.formatar()}, Idade = {float(idade):.1f} anos")
    mem.adicionar("Fator Previdenciário", fp, formula="(Tc×0,31/Es) × [1+(Id+Tc×0,31)/100]")
    mem.adicionar("RMI = SB × FP", rmi)
    return sb, fp, rmi, tc


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 1 — SISTEMA DE PONTOS (Art. 15 EC 103/2019)
# ──────────────────────────────────────────────────────────────────────────────
class RegraPonitosProgressivos(RegraTransicao):
    @property
    def nome(self) -> str:
        return "Transição — Sistema de Pontos (Art. 15 EC 103/2019)"

    @property
    def base_legal(self) -> str:
        return "EC 103/2019 Art. 15"

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)
        pontos_segurado = tc.anos_decimal + idade
        pontos_exigidos = _pontos_exigidos(segurado.sexo, der.year)
        tc_minimo = _tc_minimo(segurado.sexo)
        return pontos_segurado >= pontos_exigidos and tc.anos_decimal >= tc_minimo

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 1 — SISTEMA DE PONTOS (Art. 15)")

        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)
        pontos_segurado = tc.anos_decimal + idade
        pontos_exigidos = _pontos_exigidos(segurado.sexo, der.year)
        tc_min = _tc_minimo(segurado.sexo)
        elegivel = pontos_segurado >= pontos_exigidos and tc.anos_decimal >= tc_min

        mem.adicionar(f"Pontos do segurado: {float(pontos_segurado):.2f} "
                      f"(exigido: {pontos_exigidos})")
        mem.adicionar(f"TC mínimo: {float(tc.anos_decimal):.1f} anos (exigido: {tc_min})")

        if not elegivel:
            faltam = max(pontos_exigidos - pontos_segurado, Decimal("0"))
            mem.adicionar(f"NÃO ELEGÍVEL — faltam {float(faltam):.2f} pontos")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem,
                                  faltam_dias=int(faltam * Decimal("365.25")))

        sb, coef, rmi, tc2 = _calcular_sb_e_rmi_coef(segurado, der, mem)
        return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                              elegivel=True, rmi=rmi, rmi_teto=rmi,
                              salario_beneficio=sb, coeficiente=coef,
                              tempo_contribuicao=tc2, memoria=mem)


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 2 — IDADE MÍNIMA PROGRESSIVA (Art. 16 EC 103/2019)
# ──────────────────────────────────────────────────────────────────────────────
class RegraIdadeProgressiva(RegraTransicao):
    @property
    def nome(self) -> str:
        return "Transição — Idade Mínima Progressiva (Art. 16 EC 103/2019)"

    @property
    def base_legal(self) -> str:
        return "EC 103/2019 Art. 16"

    def _idade_minima(self, sexo: Sexo, ano: int) -> Decimal:
        from ..constantes import IDADE_PROG_EC103, IDADE_DEFINITIVA_HOMEM, IDADE_DEFINITIVA_MULHER
        if sexo == Sexo.MASCULINO:
            if ano >= 2024:
                return IDADE_DEFINITIVA_HOMEM
            base_ano = max(2020, min(ano, 2024))
            return Decimal(str(IDADE_PROG_EC103.get(base_ano, (65, 62))[0]))
        else:
            if ano >= 2031:
                return IDADE_DEFINITIVA_MULHER
            base_ano = max(2020, min(ano, 2026))
            return Decimal(str(IDADE_PROG_EC103.get(base_ano, (65, 62))[1]))

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        idade = segurado.idade_na(der)
        idade_min = self._idade_minima(segurado.sexo, der.year)
        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        tc_min = _tc_minimo(segurado.sexo)
        return idade >= idade_min and tc.anos_decimal >= tc_min

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 2 — IDADE MÍNIMA PROGRESSIVA (Art. 16)")

        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)
        idade_min = self._idade_minima(segurado.sexo, der.year)
        tc_min = _tc_minimo(segurado.sexo)
        elegivel = idade >= idade_min and tc.anos_decimal >= tc_min

        mem.adicionar(f"Idade: {float(idade):.1f} anos (mínimo: {idade_min})")
        mem.adicionar(f"TC: {float(tc.anos_decimal):.1f} anos (mínimo: {tc_min})")

        if not elegivel:
            faltam_id = max(Decimal("0"), (idade_min - idade) * Decimal("365.25"))
            faltam_tc = max(Decimal("0"), (tc_min - tc.anos_decimal) * Decimal("365.25"))
            faltam = int(max(faltam_id, faltam_tc))
            mem.adicionar("NÃO ELEGÍVEL")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem, faltam_dias=faltam)

        sb, coef, rmi, tc2 = _calcular_sb_e_rmi_coef(segurado, der, mem)
        return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                              elegivel=True, rmi=rmi, rmi_teto=rmi,
                              salario_beneficio=sb, coeficiente=coef,
                              tempo_contribuicao=tc2, memoria=mem)


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 3 — PEDÁGIO 50% + FATOR PREVIDENCIÁRIO (Art. 17 EC 103/2019)
# ──────────────────────────────────────────────────────────────────────────────
class RegraPedagio50(RegraTransicao):
    @property
    def nome(self) -> str:
        return "Transição — Pedágio 50% + FP (Art. 17 EC 103/2019)"

    @property
    def base_legal(self) -> str:
        return "EC 103/2019 Art. 17"

    def _tc_em_ec103(self, segurado: Segurado) -> Decimal:
        return _tc_em_13nov2019(segurado)

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        tc_ec103 = self._tc_em_ec103(segurado)
        limiar = _tc_minimo(segurado.sexo) - Decimal("2")  # 33H ou 28M
        return tc_ec103 >= limiar

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 3 — PEDÁGIO 50% + FP (Art. 17)")

        tc_ec103 = self._tc_em_ec103(segurado)
        tc_min = _tc_minimo(segurado.sexo)
        limiar_pedagio = tc_min - Decimal("2")

        mem.adicionar(f"TC em 13/11/2019: {float(tc_ec103):.2f} anos (limiar: {limiar_pedagio})")

        if tc_ec103 < limiar_pedagio:
            mem.adicionar("NÃO ELEGÍVEL para esta regra (TC insuficiente em 13/11/2019)")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem)

        # TC atual
        tc_atual = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        faltava_em_ec103 = max(Decimal("0"), tc_min - tc_ec103)
        pedagio = (faltava_em_ec103 * Decimal("0.5")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tc_necessario = tc_ec103 + faltava_em_ec103 + pedagio

        mem.adicionar(f"Faltava em 13/11/2019: {float(faltava_em_ec103):.2f} anos")
        mem.adicionar(f"Pedágio (50%): {float(pedagio):.2f} anos")
        mem.adicionar(f"TC necessário com pedágio: {float(tc_necessario):.2f} anos")
        mem.adicionar(f"TC atual: {float(tc_atual.anos_decimal):.2f} anos")

        elegivel = tc_atual.anos_decimal >= tc_necessario
        if not elegivel:
            faltam = max(Decimal("0"), tc_necessario - tc_atual.anos_decimal)
            mem.adicionar(f"NÃO ELEGÍVEL — faltam {float(faltam):.2f} anos de TC")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem,
                                  faltam_dias=int(faltam * Decimal("365.25")))

        sb, fp, rmi, tc2 = _calcular_sb_e_rmi_fp(segurado, der, mem)
        return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                              elegivel=True, rmi=rmi, rmi_teto=rmi,
                              salario_beneficio=sb, fator_previdenciario=fp,
                              tempo_contribuicao=tc2, memoria=mem)


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 4 — PEDÁGIO 100% + IDADE MÍNIMA (Art. 20 EC 103/2019)
# ──────────────────────────────────────────────────────────────────────────────
class RegraPedagio100(RegraTransicao):
    @property
    def nome(self) -> str:
        return "Transição — Pedágio 100% + Idade Mínima (Art. 20 EC 103/2019)"

    @property
    def base_legal(self) -> str:
        return "EC 103/2019 Art. 20"

    def _idade_minima(self, sexo: Sexo) -> Decimal:
        return Decimal("60") if sexo == Sexo.MASCULINO else Decimal("57")

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 4 — PEDÁGIO 100% + IDADE MÍNIMA (Art. 20)")

        tc_ec103 = _tc_em_13nov2019(segurado)
        tc_min = _tc_minimo(segurado.sexo)
        tc_atual = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)
        idade_min = self._idade_minima(segurado.sexo)

        faltava = max(Decimal("0"), tc_min - tc_ec103)
        tc_necessario = tc_ec103 + faltava * Decimal("2")  # pedágio 100% = dobro do que faltava

        mem.adicionar(f"TC em 13/11/2019: {float(tc_ec103):.2f} anos")
        mem.adicionar(f"Faltava: {float(faltava):.2f} anos → Pedágio 100%: {float(faltava):.2f} anos extras")
        mem.adicionar(f"TC necessário: {float(tc_necessario):.2f} anos")
        mem.adicionar(f"TC atual: {float(tc_atual.anos_decimal):.2f} anos")
        mem.adicionar(f"Idade: {float(idade):.1f} anos (mínimo: {idade_min})")

        elegivel = tc_atual.anos_decimal >= tc_necessario and idade >= idade_min

        if not elegivel:
            faltam_tc = max(Decimal("0"), tc_necessario - tc_atual.anos_decimal)
            faltam_id = max(Decimal("0"), (idade_min - idade) * Decimal("365.25"))
            faltam = int(max(faltam_tc * Decimal("365.25"), faltam_id))
            mem.adicionar("NÃO ELEGÍVEL")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem, faltam_dias=faltam)

        # RMI = 100% do SB (sem FP e sem coeficiente)
        resultado_sb = calcular_salario_beneficio(
            segurado.vinculos, der, usar_regra_ec103=True,
            aplicar_descarte=True, meses_carencia_exigidos=Carencia.APOSENTADORIA,
        )
        sb = resultado_sb["salario_beneficio"]
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)
        rmi = max(piso, min(sb, teto))

        mem.adicionar("SB", sb)
        mem.adicionar("RMI = 100% do SB (Art. 20)", rmi)

        return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                              elegivel=True, rmi=rmi, rmi_teto=rmi,
                              salario_beneficio=sb, coeficiente=Decimal("1.0"),
                              tempo_contribuicao=tc_atual, memoria=mem)

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        r = self.calcular(segurado, der)
        return r.elegivel


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 5 — DIREITO ADQUIRIDO (pré-EC 103/2019)
# ──────────────────────────────────────────────────────────────────────────────
class RegraDireitoAdquirido(RegraTransicao):
    @property
    def nome(self) -> str:
        return "Direito Adquirido — TC completo antes de 13/11/2019"

    @property
    def base_legal(self) -> str:
        return "EC 103/2019 Art. 3º; Lei 9.876/99"

    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool:
        tc_ec103 = _tc_em_13nov2019(segurado)
        return tc_ec103 >= _tc_minimo(segurado.sexo)

    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra:
        mem = MemoriaCalculo()
        mem.secao("REGRA 5 — DIREITO ADQUIRIDO (pré-EC103)")

        tc_ec103 = _tc_em_13nov2019(segurado)
        tc_min = _tc_minimo(segurado.sexo)
        elegivel = tc_ec103 >= tc_min

        mem.adicionar(f"TC em 13/11/2019: {float(tc_ec103):.2f} anos (mínimo: {tc_min})")

        if not elegivel:
            mem.adicionar("NÃO ELEGÍVEL — TC insuficiente até 13/11/2019")
            return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                                  elegivel=False, memoria=mem)

        # DIREITO ADQUIRIDO: calcula com AMBOS os regimes e escolhe o melhor
        # STF Tema 334 (RE 630.501/RS): melhor beneficio
        mem.adicionar("Direito adquirido: calculando com ambos os regimes (melhor beneficio)")

        tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
        idade = segurado.idade_na(der)
        fp = calcular_fator_previdenciario(tc.anos_decimal, idade, der)
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)

        # Opcao A: SB com regime pre-reforma (80% maiores — Lei 9.876/99)
        resultado_sb_pre = calcular_salario_beneficio(
            segurado.vinculos, der, usar_regra_ec103=False,
            aplicar_descarte=False, meses_carencia_exigidos=Carencia.APOSENTADORIA,
        )
        sb_pre = resultado_sb_pre["salario_beneficio"]
        rmi_pre = max(piso, min(sb_pre * fp, teto))

        # Opcao B: SB com regime EC 103 (100% dos salarios + descarte)
        resultado_sb_ec103 = calcular_salario_beneficio(
            segurado.vinculos, der, usar_regra_ec103=True,
            aplicar_descarte=True, meses_carencia_exigidos=Carencia.APOSENTADORIA,
        )
        sb_ec103 = resultado_sb_ec103["salario_beneficio"]
        rmi_ec103 = max(piso, min(sb_ec103 * fp, teto))

        mem.adicionar(f"Regime pre-reforma (80% maiores): SB = R$ {float(sb_pre):.2f} → RMI = R$ {float(rmi_pre):.2f}")
        mem.adicionar(f"Regime EC 103 (100% + descarte): SB = R$ {float(sb_ec103):.2f} → RMI = R$ {float(rmi_ec103):.2f}")

        # Eleger o melhor
        if rmi_pre >= rmi_ec103:
            sb, rmi = sb_pre, rmi_pre
            mem.adicionar(f"ELEITO: regime pre-reforma (mais vantajoso)",
                          formula="STF Tema 334 — direito ao melhor beneficio")
        else:
            sb, rmi = sb_ec103, rmi_ec103
            mem.adicionar(f"ELEITO: regime EC 103 (mais vantajoso)",
                          formula="STF Tema 334 — direito ao melhor beneficio")

        mem.adicionar(f"FP = {float(fp):.4f}", formula="(Tc×0,31/Es) × [1+(Id+Tc×0,31)/100]")
        mem.adicionar(f"RMI final = R$ {float(rmi):.2f}")

        return ResultadoRegra(nome_regra=self.nome, base_legal=self.base_legal,
                              elegivel=True, rmi=rmi, rmi_teto=rmi,
                              salario_beneficio=sb, fator_previdenciario=fp,
                              tempo_contribuicao=tc, memoria=mem)
