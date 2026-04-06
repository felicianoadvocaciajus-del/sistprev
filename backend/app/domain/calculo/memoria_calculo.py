"""
Memória de Cálculo Detalhada — Correção Monetária dos Salários de Contribuição.

Gera tabela mês a mês com:
  - Competência (mês/ano)
  - Salário original
  - Índice de correção (INPC acumulado até a DER)
  - Salário corrigido
  - Indicação se foi limitado ao teto
  - Indicação se foi descartado (Art. 26 §6 EC 103/2019)

Fundamentação:
  - Art. 29 Lei 8.213/91
  - Art. 26 §6 EC 103/2019 (descarte automático)
  - INPC como índice de correção (Art. 29-B Lei 8.213/91)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class LinhaMemoria:
    """Uma linha da memória de cálculo."""
    competencia: date
    salario_original: Decimal
    indice_correcao: Decimal
    salario_corrigido: Decimal
    teto_vigente: Decimal
    limitado_teto: bool = False
    descartado: bool = False
    motivo_descarte: str = ""
    vinculo_nome: str = ""


def gerar_memoria_calculo(
    contribuicoes: List[Dict[str, Any]],
    der: date,
    sexo: str = "masculino",
    aplicar_descarte: bool = True,
) -> Dict[str, Any]:
    """
    Gera memória de cálculo completa com correção monetária e descarte automático.

    Args:
        contribuicoes: list of dicts with 'competencia' (date), 'salario' (Decimal), 'vinculo_nome' (str)
        der: Data de Entrada do Requerimento
        sexo: 'masculino' ou 'feminino'
        aplicar_descarte: se True, aplica descarte do Art. 26 §6 EC 103/2019

    Returns:
        dict with linhas, totais, descarte info, média
    """
    # Filter contributions from July 1994 onwards (Plano Real)
    PLANO_REAL = date(1994, 7, 1)

    linhas: List[LinhaMemoria] = []

    for c in contribuicoes:
        comp = c.get("competencia")
        if isinstance(comp, str):
            try:
                partes = comp.split("/")
                if len(partes) == 2:
                    comp = date(int(partes[1]), int(partes[0]), 1)
                elif len(partes) == 3:
                    comp = date(int(partes[2]), int(partes[1]), 1)
            except:
                continue

        if not isinstance(comp, date) or comp < PLANO_REAL:
            continue

        sal = Decimal(str(c.get("salario", "0")))
        if sal <= 0:
            continue

        indice = _obter_indice_correcao(comp, der)
        corrigido = (sal * indice).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        teto = _teto_na_competencia(comp)
        limitado = sal > teto
        if limitado:
            corrigido = (teto * indice).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        linhas.append(LinhaMemoria(
            competencia=comp,
            salario_original=sal,
            indice_correcao=indice,
            salario_corrigido=corrigido,
            teto_vigente=teto,
            limitado_teto=limitado,
            vinculo_nome=c.get("vinculo_nome", ""),
        ))

    # Sort by competência
    linhas.sort(key=lambda l: l.competencia)

    total_contribuicoes = len(linhas)

    # Calculate média dos 80% maiores (regra pré-reforma) and 100% (pós-reforma)
    corrigidos_ordenados = sorted(linhas, key=lambda l: l.salario_corrigido, reverse=True)

    # Média 80% maiores
    n80 = max(1, int(total_contribuicoes * 0.8))
    maiores_80 = corrigidos_ordenados[:n80]
    media_80 = sum(l.salario_corrigido for l in maiores_80) / Decimal(str(len(maiores_80))) if maiores_80 else Decimal("0")
    media_80 = media_80.quantize(Decimal("0.01"))

    # Média 100%
    media_100 = sum(l.salario_corrigido for l in linhas) / Decimal(str(total_contribuicoes)) if linhas else Decimal("0")
    media_100 = media_100.quantize(Decimal("0.01"))

    # ═══════════════════════════════════════════════════════════
    # DESCARTE AUTOMÁTICO (Art. 26 §6 EC 103/2019)
    # ═══════════════════════════════════════════════════════════
    descarte_info = {
        "aplicado": False,
        "fundamentacao": "Art. 26, §6º, EC 103/2019",
        "total_descartados": 0,
        "economia_mensal": Decimal("0"),
        "media_com_descarte": Decimal("0"),
        "media_sem_descarte": media_100,
    }

    if aplicar_descarte and der >= date(2019, 11, 13):
        # The rule: discard contributions that REDUCE the benefit average,
        # as long as the minimum TC for the rule is maintained

        # Minimum TC requirement (in months) - simplified
        tc_minimo_meses = 180  # 15 years = minimum carência

        # Sort ascending to find lowest values
        if total_contribuicoes > tc_minimo_meses:
            # Try discarding lowest contributions one by one
            linhas_para_descarte = sorted(linhas, key=lambda l: l.salario_corrigido)
            descartaveis = total_contribuicoes - tc_minimo_meses

            melhor_media = media_100
            qtd_descartar = 0

            for i in range(1, descartaveis + 1):
                restantes = sorted(linhas, key=lambda l: l.salario_corrigido, reverse=True)[:total_contribuicoes - i]
                if not restantes:
                    break
                media_teste = sum(l.salario_corrigido for l in restantes) / Decimal(str(len(restantes)))
                if media_teste > melhor_media:
                    melhor_media = media_teste
                    qtd_descartar = i
                else:
                    break  # No more improvement

            if qtd_descartar > 0:
                # Mark discarded
                menores = sorted(linhas, key=lambda l: l.salario_corrigido)[:qtd_descartar]
                for m in menores:
                    m.descartado = True
                    m.motivo_descarte = "Descarte automático — Art. 26, §6º, EC 103/2019"

                media_com_descarte = melhor_media.quantize(Decimal("0.01"))
                descarte_info["aplicado"] = True
                descarte_info["total_descartados"] = qtd_descartar
                descarte_info["media_com_descarte"] = media_com_descarte
                descarte_info["economia_mensal"] = (media_com_descarte - media_100).quantize(Decimal("0.01"))

    # Serialize
    linhas_serial = []
    for l in linhas:
        linhas_serial.append({
            "competencia": l.competencia.strftime("%m/%Y"),
            "salario_original": str(l.salario_original),
            "indice_correcao": str(l.indice_correcao),
            "salario_corrigido": str(l.salario_corrigido),
            "teto_vigente": str(l.teto_vigente),
            "limitado_teto": l.limitado_teto,
            "descartado": l.descartado,
            "motivo_descarte": l.motivo_descarte,
            "vinculo_nome": l.vinculo_nome,
        })

    return {
        "linhas": linhas_serial,
        "total_contribuicoes": total_contribuicoes,
        "total_descartados": descarte_info["total_descartados"],
        "media_80_maiores": str(media_80),
        "media_100": str(media_100),
        "media_com_descarte": str(descarte_info.get("media_com_descarte", media_100)),
        "descarte": {
            "aplicado": descarte_info["aplicado"],
            "total_descartados": descarte_info["total_descartados"],
            "economia_mensal": str(descarte_info["economia_mensal"]),
            "fundamentacao": descarte_info["fundamentacao"],
        },
        "fundamentacao": "Art. 29, I e II, Lei 8.213/91; Art. 26 EC 103/2019",
    }


def _obter_indice_correcao(competencia: date, der: date) -> Decimal:
    """
    Returns the INPC accumulated correction index from competência to DER.
    Uses a simplified approximation based on annual INPC rates.
    """
    # Simplified annual INPC rates (approximate)
    INPC_ANUAL = {
        1994: Decimal("22.41"), 1995: Decimal("22.41"), 1996: Decimal("9.12"),
        1997: Decimal("4.34"), 1998: Decimal("2.49"), 1999: Decimal("8.43"),
        2000: Decimal("5.27"), 2001: Decimal("9.44"), 2002: Decimal("14.74"),
        2003: Decimal("10.38"), 2004: Decimal("6.13"), 2005: Decimal("5.05"),
        2006: Decimal("2.81"), 2007: Decimal("5.15"), 2008: Decimal("6.48"),
        2009: Decimal("4.11"), 2010: Decimal("6.47"), 2011: Decimal("6.08"),
        2012: Decimal("6.20"), 2013: Decimal("5.56"), 2014: Decimal("6.23"),
        2015: Decimal("11.28"), 2016: Decimal("6.58"), 2017: Decimal("2.07"),
        2018: Decimal("3.43"), 2019: Decimal("4.48"), 2020: Decimal("5.45"),
        2021: Decimal("10.16"), 2022: Decimal("5.93"), 2023: Decimal("3.71"),
        2024: Decimal("4.77"), 2025: Decimal("4.50"), 2026: Decimal("4.00"),
    }

    indice = Decimal("1")
    ano_inicio = competencia.year
    ano_fim = der.year

    for ano in range(ano_inicio, ano_fim + 1):
        taxa = INPC_ANUAL.get(ano, Decimal("4.00"))

        if ano == ano_inicio and ano == ano_fim:
            # Proportional
            meses = der.month - competencia.month
            if meses <= 0:
                meses = 1
            fator = Decimal("1") + (taxa / Decimal("100")) * Decimal(str(meses)) / Decimal("12")
        elif ano == ano_inicio:
            meses_restantes = 12 - competencia.month + 1
            fator = Decimal("1") + (taxa / Decimal("100")) * Decimal(str(meses_restantes)) / Decimal("12")
        elif ano == ano_fim:
            meses_ate = der.month
            fator = Decimal("1") + (taxa / Decimal("100")) * Decimal(str(meses_ate)) / Decimal("12")
        else:
            fator = Decimal("1") + taxa / Decimal("100")

        indice *= fator

    return indice.quantize(Decimal("0.000001"))


def _teto_na_competencia(comp: date) -> Decimal:
    """Returns the INSS contribution ceiling for a given month."""
    # Key historical ceiling values
    TETOS = [
        (date(2024, 1, 1), Decimal("7786.02")),
        (date(2023, 1, 1), Decimal("7507.49")),
        (date(2022, 1, 1), Decimal("7087.22")),
        (date(2021, 1, 1), Decimal("6433.57")),
        (date(2020, 2, 1), Decimal("6101.06")),
        (date(2020, 1, 1), Decimal("5839.45")),
        (date(2019, 1, 1), Decimal("5839.45")),
        (date(2018, 1, 1), Decimal("5645.80")),
        (date(2017, 1, 1), Decimal("5531.31")),
        (date(2016, 1, 1), Decimal("5189.82")),
        (date(2015, 1, 1), Decimal("4663.75")),
        (date(2014, 1, 1), Decimal("4390.24")),
        (date(2013, 1, 1), Decimal("4159.00")),
        (date(2012, 1, 1), Decimal("3916.20")),
        (date(2011, 1, 1), Decimal("3689.66")),
        (date(2010, 1, 1), Decimal("3467.40")),
        (date(2009, 2, 1), Decimal("3218.90")),
        (date(2008, 3, 1), Decimal("3038.99")),
        (date(2007, 4, 1), Decimal("2894.28")),
        (date(2006, 4, 1), Decimal("2801.56")),
        (date(2005, 5, 1), Decimal("2668.15")),
        (date(2004, 5, 1), Decimal("2508.72")),
        (date(2003, 6, 1), Decimal("1869.34")),
        (date(2002, 6, 1), Decimal("1561.56")),
        (date(2001, 6, 1), Decimal("1430.00")),
        (date(2000, 6, 1), Decimal("1328.25")),
        (date(1999, 6, 1), Decimal("1255.32")),
        (date(1998, 12, 16), Decimal("1200.00")),
        (date(1998, 6, 1), Decimal("1081.50")),
        (date(1997, 6, 1), Decimal("1031.87")),
        (date(1996, 5, 1), Decimal("957.56")),
        (date(1995, 5, 1), Decimal("832.66")),
        (date(1994, 7, 1), Decimal("582.86")),
    ]

    for data_inicio, teto in TETOS:
        if comp >= data_inicio:
            return teto

    return Decimal("582.86")
