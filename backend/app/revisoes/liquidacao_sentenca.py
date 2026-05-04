"""
Liquidação de Sentença Previdenciária — Cálculo de Atrasados.

Calcula parcelas vencidas entre a DIB (Data de Início do Benefício)
e a data de competência mais recente, com:

  Correção monetária: INPC (parcelas previdenciárias)
  Juros de mora:
    - 0,5% a.m. até 06/2009 (Lei 9.494/97 e EC 20/98)
    - TR + 0,5% a.m. de 07/2009 até 12/2021
    - SELIC a partir de 01/2022 (EC 113/2021 e RE 870.947/SE STF)

Prescrição: 5 anos (Decreto 20.910/32) — parcelas anteriores a 5 anos
da data do ajuizamento da ação são prescritas.

Conforme Manual de Cálculos da Justiça Federal — CJF Resolução 963/2025.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from ..domain.models.contribuicao import Competencia
from ..domain.indices.correcao_monetaria import INDICES_INPC, fator_acumulado
from ..domain.models.resultado import MemoriaCalculo


def _D(s: str) -> Decimal:
    return Decimal(s)


# Taxa SELIC mensal acumulada (para pós-EC 113/2021)
# Fonte: BACEN SGS Série 4189
# Aqui usamos um dicionário resumido; idealmente atualizado via API BACEN.
SELIC_MENSAL: dict = {
    # 2022
    (2022, 1): _D("1.0073"), (2022, 2): _D("1.0082"), (2022, 3): _D("1.0108"),
    (2022, 4): _D("1.0084"), (2022, 5): _D("1.0114"), (2022, 6): _D("1.0108"),
    (2022, 7): _D("1.0107"), (2022, 8): _D("1.0114"), (2022, 9): _D("1.0108"),
    (2022, 10): _D("1.0114"), (2022, 11): _D("1.0108"), (2022, 12): _D("1.0114"),
    # 2023
    (2023, 1): _D("1.0112"), (2023, 2): _D("1.0096"), (2023, 3): _D("1.0112"),
    (2023, 4): _D("1.0106"), (2023, 5): _D("1.0112"), (2023, 6): _D("1.0106"),
    (2023, 7): _D("1.0107"), (2023, 8): _D("1.0113"), (2023, 9): _D("1.0100"),
    (2023, 10): _D("1.0092"), (2023, 11): _D("1.0092"), (2023, 12): _D("1.0092"),
    # 2024
    (2024, 1): _D("1.0087"), (2024, 2): _D("1.0082"), (2024, 3): _D("1.0082"),
    (2024, 4): _D("1.0082"), (2024, 5): _D("1.0082"), (2024, 6): _D("1.0082"),
    (2024, 7): _D("1.0082"), (2024, 8): _D("1.0087"), (2024, 9): _D("1.0088"),
    (2024, 10): _D("1.0093"), (2024, 11): _D("1.0099"), (2024, 12): _D("1.0099"),
    # 2025
    (2025, 1): _D("1.0104"), (2025, 2): _D("1.0110"), (2025, 3): _D("1.0115"),
    (2025, 4): _D("1.0115"), (2025, 5): _D("1.0115"), (2025, 6): _D("1.0115"),
    (2025, 7): _D("1.0115"), (2025, 8): _D("1.0115"), (2025, 9): _D("1.0115"),
    (2025, 10): _D("1.0115"), (2025, 11): _D("1.0115"), (2025, 12): _D("1.0115"),
}


def calcular_atrasados(
    dib: date,
    rmi_original: Decimal,
    data_atualizacao: date,
    data_ajuizamento: Optional[date] = None,
    incluir_juros: bool = True,
    rmi_paga: Optional[Decimal] = None,
) -> dict:
    """
    Calcula as parcelas atrasadas de um benefício previdenciário.

    IMPORTANTE: Os atrasados incidem sobre a DIFERENÇA entre a RMI correta
    e a RMI que vinha sendo paga, NÃO sobre o benefício integral.

    Se rmi_paga for informada:
      valor_base = rmi_original (correta) - rmi_paga (errada)
    Se rmi_paga NÃO for informada:
      valor_base = rmi_original (caso de benefício não concedido — todo o valor é devido)

    dib: Data de Início do Benefício
    rmi_original: RMI correta (como deveria ter sido calculada)
    data_atualizacao: data até onde calcular (geralmente hoje)
    data_ajuizamento: data do protocolo da ação (para prescrição quinquenal)
    incluir_juros: True para incluir juros de mora
    rmi_paga: RMI que o INSS vinha pagando (se revisão). Se None, usa rmi_original integral.

    Retorna dict com:
      parcelas: list de dicts (competência, valor_base, correção, juros, total)
      total_principal: soma das parcelas sem juros
      total_juros: soma dos juros
      total_geral: total com correção e juros
      parcelas_prescritas: int
      tipo_calculo: 'diferenca' ou 'integral'
    """
    mem = MemoriaCalculo()
    mem.secao("LIQUIDACAO DE SENTENCA -- CALCULO DE ATRASADOS")

    # Determinar valor base: diferença ou integral
    if rmi_paga is not None and rmi_paga > Decimal("0"):
        valor_base_mensal = (rmi_original - rmi_paga).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tipo_calculo = "diferenca"
        if valor_base_mensal <= Decimal("0"):
            return {
                "parcelas": [],
                "total_principal": Decimal("0"),
                "total_juros": Decimal("0"),
                "total_geral": Decimal("0"),
                "parcelas_calculadas": 0,
                "parcelas_prescritas": 0,
                "tipo_calculo": tipo_calculo,
                "rmi_correta": rmi_original,
                "rmi_paga": rmi_paga,
                "diferenca_mensal": Decimal("0"),
                "explicacao": "A RMI paga ja e igual ou superior a RMI correta. Nao ha diferenca a cobrar.",
                "memoria": mem,
            }
        mem.adicionar(f"RMI correta (devida): R$ {rmi_original}")
        mem.adicionar(f"RMI paga pelo INSS: R$ {rmi_paga}")
        mem.adicionar(f"Diferenca mensal: R$ {valor_base_mensal}")
        mem.adicionar("ATRASADOS INCIDEM SOBRE A DIFERENCA, NAO SOBRE O BENEFICIO INTEGRAL")
    else:
        valor_base_mensal = rmi_original
        tipo_calculo = "integral"
        mem.adicionar(f"RMI devida (integral): R$ {rmi_original}")
        mem.adicionar("Beneficio nao concedido -- atrasados sobre o valor integral")

    # Prescrição: 5 anos retroativos a partir do ajuizamento
    data_prescricao = None
    if data_ajuizamento:
        ano_presc = data_ajuizamento.year - 5
        data_prescricao = date(ano_presc, data_ajuizamento.month, data_ajuizamento.day)

    # Parcelas vencidas: intervalo half-open [DIB, data_atualizacao).
    # A competencia de data_atualizacao ainda nao venceu, nao entra no atrasado.
    data_atualizacao_norm = date(data_atualizacao.year, data_atualizacao.month, 1)
    competencias = [
        c for c in Competencia.intervalo(dib, data_atualizacao)
        if c < data_atualizacao_norm
    ]
    parcelas = []
    total_principal = Decimal("0")
    total_juros = Decimal("0")
    parcelas_prescritas = 0

    for comp in competencias:
        # Verificar prescrição
        if data_prescricao and comp < date(data_prescricao.year, data_prescricao.month, 1):
            parcelas_prescritas += 1
            continue

        # Valor base (DIFERENÇA) corrigido pelo INPC até a data de atualização
        fator_corr = fator_acumulado(
            (comp.year, comp.month),
            (data_atualizacao.year, data_atualizacao.month)
        )
        valor_corrigido = (valor_base_mensal * fator_corr).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Juros de mora
        juros = Decimal("0")
        if incluir_juros:
            juros = _calcular_juros(comp, data_atualizacao, valor_corrigido)

        total_parcela = valor_corrigido + juros
        total_principal += valor_corrigido
        total_juros += juros

        parcelas.append({
            "competencia": Competencia.formatar(comp),
            "valor_base": valor_base_mensal,
            "fator_correcao": fator_corr,
            "valor_corrigido": valor_corrigido,
            "juros": juros,
            "total_parcela": total_parcela,
        })

    total_geral = (total_principal + total_juros).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_principal = total_principal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_juros = total_juros.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    mem.adicionar(f"DIB: {dib.strftime('%d/%m/%Y')}")
    mem.adicionar(f"Competencias calculadas: {len(parcelas)}")
    if parcelas_prescritas:
        mem.adicionar(f"Parcelas prescritas (>5 anos): {parcelas_prescritas}")
    mem.adicionar("Total Principal (corrigido)", total_principal)
    mem.adicionar("Total Juros", total_juros)
    mem.adicionar("TOTAL GERAL", total_geral)

    result = {
        "parcelas": parcelas,
        "total_principal": total_principal,
        "total_juros": total_juros,
        "total_geral": total_geral,
        "parcelas_calculadas": len(parcelas),
        "parcelas_prescritas": parcelas_prescritas,
        "tipo_calculo": tipo_calculo,
        "memoria": mem,
    }

    if tipo_calculo == "diferenca":
        result["rmi_correta"] = rmi_original
        result["rmi_paga"] = rmi_paga
        result["diferenca_mensal"] = valor_base_mensal
        result["explicacao"] = (
            f"Atrasados calculados sobre a DIFERENCA mensal de R$ {valor_base_mensal} "
            f"(RMI correta R$ {rmi_original} - RMI paga R$ {rmi_paga}). "
            f"Cada parcela = diferenca x fator INPC + juros. "
            f"Conforme Manual de Calculos da Justica Federal."
        )

    return result


def _calcular_juros(comp: date, data_ref: date, valor_base: Decimal) -> Decimal:
    """
    Calcula os juros de mora sobre uma parcela.

    Regimes:
      - até 06/2009: 0,5% a.m. (simples)
      - 07/2009 a 12/2021: TR + 0,5% a.m.
      - a partir de 01/2022: SELIC (EC 113/2021)
    """
    EC113_VIGENCIA = date(2022, 1, 1)
    JUROS_MUDANCA_2009 = date(2009, 7, 1)

    if comp >= EC113_VIGENCIA:
        # SELIC acumulada desde a competência até data_ref
        fator_selic = _selic_acumulada(comp, data_ref)
        return (valor_base * (fator_selic - Decimal("1"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    elif comp >= JUROS_MUDANCA_2009:
        # TR + 0,5% a.m. — aproximação: usando 0,5% a.m. simples + TR ≈ 0
        # Na prática a TR ficou próxima de 0 por muitos anos
        meses = Competencia.diferenca_meses(comp, date(data_ref.year, data_ref.month, 1))
        taxa_mensal = _D("0.005")
        return (valor_base * taxa_mensal * Decimal(str(meses))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        # 0,5% a.m. simples até 06/2009
        meses = min(
            Competencia.diferenca_meses(comp, date(data_ref.year, data_ref.month, 1)),
            Competencia.diferenca_meses(comp, JUROS_MUDANCA_2009),
        )
        taxa_mensal = _D("0.005")
        return (valor_base * taxa_mensal * Decimal(str(max(0, meses)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


def _selic_acumulada(comp: date, data_ref: date) -> Decimal:
    """SELIC acumulada desde a competência até data_ref."""
    fator = _D("1")
    atual = comp
    fim = date(data_ref.year, data_ref.month, 1)
    while atual <= fim:
        key = (atual.year, atual.month)
        taxa = SELIC_MENSAL.get(key, _D("1.01"))  # fallback conservador
        fator = fator * taxa
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)
    return fator
