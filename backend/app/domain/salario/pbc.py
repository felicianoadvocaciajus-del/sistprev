"""
Período Básico de Cálculo (PBC) — Art. 29 Lei 8.213/91.

Define quais salários de contribuição entram no cálculo do salário de benefício.

Três regras conforme a época de filiação e a data do benefício:

  REGRA 1 (pré-Lei 9.876/99):
    Benefícios com DIB anterior a 29/11/1999.
    PBC = 36 maiores SC nos últimos 48 meses.

  REGRA 2 (transição Lei 9.876/99 — Art. 3º):
    Segurados que já eram filiados antes de 29/11/1999.
    PBC = todos os SC desde jul/1994 até o mês anterior à DER.
    Usa 80% maiores + divisor mínimo.

  REGRA 3 (EC 103/2019 — Art. 26):
    Regra permanente pós-reforma.
    PBC = todos os SC desde jul/1994 até o mês anterior à DER.
    Usa 100% dos SC (sem descarte, exceto pelo Art. 26 §6º).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from ..models.contribuicao import Contribuicao, Competencia
from ..models.vinculo import Vinculo
from ..indices import teto_em, corrigir_salario
from ..constantes import DatasCorte, DIVISOR_MINIMO_PERCENTUAL


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO E CORREÇÃO DE SALÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

def extrair_e_corrigir_salarios(
    vinculos: List[Vinculo],
    der: date,
    incluir_pre_1994: bool = False,
) -> List[Contribuicao]:
    """
    Extrai todos os salários de contribuição dos vínculos,
    aplica o teto, corrige monetariamente até a DER e retorna lista ordenada.

    incluir_pre_1994: True para a tese da Revisão da Vida Toda.
    """
    marco = DatasCorte.PLANO_REAL  # jul/1994

    # Mês anterior à DER é o último mês do PBC
    mes_anterior_der = Competencia.anterior(date(der.year, der.month, 1))

    salarios: List[Contribuicao] = []

    for v in vinculos:
        for c in v.contribuicoes:
            # Filtro de data
            if c.competencia > mes_anterior_der:
                continue
            if not incluir_pre_1994 and c.competencia < marco:
                continue
            if not c.valida_tc:
                continue  # não entra no PBC

            # Aplicar teto vigente
            teto = teto_em(c.competencia.year, c.competencia.month)
            sc_limitado = min(c.salario_contribuicao, teto)

            # Corrigir monetariamente até a DER
            sc_corrigido = corrigir_salario(sc_limitado, c.competencia, der)

            contrib = Contribuicao(
                competencia=c.competencia,
                salario_contribuicao=c.salario_contribuicao,
                teto_aplicado=teto,
                salario_corrigido=sc_corrigido,
                indice_correcao=(sc_corrigido / sc_limitado) if sc_limitado > 0 else Decimal("1"),
                valida_carencia=c.valida_carencia,
                valida_tc=c.valida_tc,
                observacao=c.observacao,
            )
            salarios.append(contrib)

    # Remover duplicatas por competência (pegar o maior SC do mês, se houver)
    salarios = _deduplicar_por_competencia(salarios)
    return sorted(salarios)


def _deduplicar_por_competencia(salarios: List[Contribuicao]) -> List[Contribuicao]:
    """Se houver dois vínculos no mesmo mês, usa o maior salário."""
    por_competencia: dict[date, Contribuicao] = {}
    for c in salarios:
        if c.competencia not in por_competencia:
            por_competencia[c.competencia] = c
        else:
            existente = por_competencia[c.competencia]
            if c.salario_corrigido > existente.salario_corrigido:
                por_competencia[c.competencia] = c
    return list(por_competencia.values())


# ─────────────────────────────────────────────────────────────────────────────
# SELEÇÃO DO PBC (80% maiores — pré-EC103)
# ─────────────────────────────────────────────────────────────────────────────

def selecionar_80_maiores(salarios: List[Contribuicao]) -> Tuple[List[Contribuicao], int]:
    """
    Seleciona os 80% maiores salários corrigidos do PBC.
    Retorna (salarios_selecionados, divisor_utilizado).

    Divisor = max(60% × total_meses_PBC, quantidade_selecionada)
    Conforme Lei 9.876/99 Art. 29 §§ 5º e 6º.
    """
    if not salarios:
        return [], 0

    n_total = len(salarios)
    n_80_porcento = max(1, round(n_total * 0.80))

    # Ordenar por salário corrigido (maior primeiro)
    ordenados = sorted(salarios, key=lambda c: c.salario_corrigido, reverse=True)
    selecionados = ordenados[:n_80_porcento]

    # Divisor mínimo: 60% do total do PBC
    divisor_minimo = int((DIVISOR_MINIMO_PERCENTUAL * Decimal(str(n_total))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ))
    divisor = max(divisor_minimo, n_80_porcento)

    return selecionados, divisor


def calcular_media_pre_ec103(salarios_pbc: List[Contribuicao]) -> Tuple[Decimal, int, List[Contribuicao]]:
    """
    Calcula a média dos 80% maiores salários com divisor mínimo (regra pré-EC 103).
    Retorna (media, divisor_utilizado, salarios_selecionados).
    """
    selecionados, divisor = selecionar_80_maiores(salarios_pbc)
    if divisor == 0:
        return Decimal("0"), 0, []

    soma = sum(c.salario_corrigido for c in selecionados)
    media = (soma / Decimal(str(divisor))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return media, divisor, selecionados


# ─────────────────────────────────────────────────────────────────────────────
# SELEÇÃO DO PBC (100% — pós-EC103)
# ─────────────────────────────────────────────────────────────────────────────

def calcular_media_pos_ec103(salarios_pbc: List[Contribuicao]) -> Tuple[Decimal, int]:
    """
    Calcula a média de 100% dos salários do PBC (regra permanente EC 103/2019).
    Art. 26 §1º EC 103: média aritmética simples de todos os SC.
    Retorna (media, n_salarios).
    """
    if not salarios_pbc:
        return Decimal("0"), 0

    n = len(salarios_pbc)
    soma = sum(c.salario_corrigido for c in salarios_pbc)
    media = (soma / Decimal(str(n))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return media, n


# ─────────────────────────────────────────────────────────────────────────────
# DESCARTE EC 103/2019 — Art. 26 §6º
# ─────────────────────────────────────────────────────────────────────────────

def aplicar_descarte_ec103(
    salarios_pbc: List[Contribuicao],
    meses_carencia_exigidos: int = 180,
) -> Tuple[List[Contribuicao], Decimal, int]:
    """
    Art. 26 §6º EC 103/2019: o segurado pode descartar contribuições
    de menor valor, desde que:
    1. Os descartados não sejam necessários para completar a carência.
    2. O descarte aumente (ou não diminua) a média.

    Algoritmo:
    - Ordena por salário corrigido (menor primeiro)
    - Remove um a um se a média aumenta e a carência ainda está OK
    - Para quando o descarte diminui a média

    Retorna (salarios_apos_descarte, media_resultante, n_descartados).
    """
    if not salarios_pbc:
        return [], Decimal("0"), 0

    salarios = sorted(salarios_pbc, key=lambda c: c.salario_corrigido)
    media_atual, _ = calcular_media_pos_ec103(salarios)
    descartados = 0

    for i in range(len(salarios)):
        candidato_descarte = salarios[i]
        restantes = salarios[i + 1:]

        # Verificar carência: não pode descartar se reduzir abaixo do mínimo
        meses_restantes = sum(1 for c in restantes if c.valida_carencia)
        if meses_restantes < meses_carencia_exigidos:
            break

        # Verificar se a média aumenta ou fica igual
        if not restantes:
            break
        nova_media, _ = calcular_media_pos_ec103(restantes)
        if nova_media > media_atual:
            media_atual = nova_media
            descartados += 1
        else:
            # Descarte não ajuda mais — parar
            salarios = salarios[i:]
            return salarios, media_atual, descartados

    return salarios[descartados:], media_atual, descartados


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES PÚBLICAS PRINCIPAIS
# ─────────────────────────────────────────────────────────────────────────────

def calcular_salario_beneficio(
    vinculos: List[Vinculo],
    der: date,
    usar_regra_ec103: bool = True,
    incluir_pre_1994: bool = False,
    aplicar_descarte: bool = True,
    meses_carencia_exigidos: int = 180,
) -> dict:
    """
    Calcula o Salário de Benefício (SB) conforme a regra aplicável.

    Retorna dict com:
      salario_beneficio: Decimal
      media: Decimal
      n_salarios: int
      divisor: int
      salarios_pbc: List[Contribuicao]  — salários usados
      salarios_descartados: int
      regra_aplicada: str
    """
    salarios = extrair_e_corrigir_salarios(vinculos, der, incluir_pre_1994)

    if not salarios:
        return {
            "salario_beneficio": Decimal("0"),
            "media": Decimal("0"),
            "n_salarios": 0,
            "divisor": 0,
            "salarios_pbc": [],
            "salarios_descartados": 0,
            "regra_aplicada": "Sem salários no PBC",
        }

    if usar_regra_ec103:
        # Regra EC 103/2019: 100% dos SC com possível descarte
        if aplicar_descarte:
            salarios_finais, media, n_desc = aplicar_descarte_ec103(
                salarios, meses_carencia_exigidos
            )
        else:
            salarios_finais = salarios
            media, _ = calcular_media_pos_ec103(salarios)
            n_desc = 0

        return {
            "salario_beneficio": media,
            "media": media,
            "n_salarios": len(salarios_finais),
            "divisor": len(salarios_finais),
            "salarios_pbc": salarios_finais,
            "salarios_descartados": n_desc,
            "regra_aplicada": "EC 103/2019 — Art. 26 (100% dos SC desde jul/1994)",
        }
    else:
        # Regra pré-EC 103: 80% maiores com divisor mínimo
        media, divisor, selecionados = calcular_media_pre_ec103(salarios)
        return {
            "salario_beneficio": media,
            "media": media,
            "n_salarios": len(selecionados),
            "divisor": divisor,
            "salarios_pbc": selecionados,
            "salarios_descartados": len(salarios) - len(selecionados),
            "regra_aplicada": "Lei 9.876/99 — Art. 29 (80% maiores SC desde jul/1994)",
        }
