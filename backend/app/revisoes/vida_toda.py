"""
Revisão da Vida Toda — Tema 1.102 STF / Tema 999 STJ.

Compara dois métodos de cálculo do salário de benefício:

  MÉTODO ORIGINAL (regra de transição Lei 9.876/99 Art. 3º):
    PBC = salários desde jul/1994 até DER
    Usa 80% maiores com divisor mínimo.

  MÉTODO VIDA TODA (regra permanente Lei 8.213/91 Art. 29):
    PBC = TODOS os salários desde a primeira contribuição (inclui pré-1994)
    Usa 80% maiores SEM divisor mínimo.
    Correção monetária histórica aplicada desde a primeira contribuição.

A revisão só é favorável quando os salários pré-1994 eram MAIORES
que a média do período pós-1994.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from ..domain.models.segurado import Segurado
from ..domain.models.resultado import ResultadoRegra, MemoriaCalculo, DispositivoLegal
from ..domain.salario.pbc import (
    extrair_e_corrigir_salarios,
    selecionar_80_maiores,
    calcular_media_pre_ec103,
)
from ..domain.indices import teto_na_data
from ..domain.indices.salario_minimo import salario_minimo_na_data
from ..domain.fator_previdenciario import calcular_coeficiente, rmi_com_coeficiente
from ..domain.tempo import calcular_tempo_contribuicao
from ..domain.constantes import Carencia, DatasCorte


def calcular_revisao_vida_toda(
    segurado: Segurado,
    der: date,
    dib: date,
    rmi_original: Optional[Decimal] = None,
) -> dict:
    """
    Calcula a Revisão da Vida Toda e retorna o resultado comparativo.

    Retorna dict com:
      metodo_original: ResultadoRegra
      metodo_vida_toda: ResultadoRegra
      favoravel: bool  — True se Vida Toda resulta em RMI maior
      diferenca_rmi: Decimal  — diferença mensal (positivo = Vida Toda é melhor)
      resultado_final: ResultadoRegra  — o mais vantajoso
    """
    # ── MÉTODO ORIGINAL (pós-jul/1994, 80% com divisor mínimo) ───────────────
    mem_orig = MemoriaCalculo()
    mem_orig.secao("MÉTODO ORIGINAL — Transição Lei 9.876/99 Art. 3º")

    salarios_pos94 = extrair_e_corrigir_salarios(segurado.vinculos, der, incluir_pre_1994=False)
    media_orig, divisor_orig, sel_orig = calcular_media_pre_ec103(salarios_pos94)

    tc = calcular_tempo_contribuicao(segurado.vinculos, der, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)
    coef = calcular_coeficiente(tc.anos_decimal, segurado.sexo)
    teto = teto_na_data(der)
    piso = salario_minimo_na_data(der)

    rmi_orig = rmi_com_coeficiente(media_orig, coef, teto, piso)

    mem_orig.adicionar(f"Salários no PBC (pós-jul/1994): {len(salarios_pos94)}")
    mem_orig.adicionar(f"Selecionados (80%): {len(sel_orig)} | Divisor: {divisor_orig}")
    mem_orig.adicionar("Média", media_orig,
                       fundamentacao=DispositivoLegal(
                           "Lei 9.876/99", "Art. 3º",
                           "Regra de transição: 80% maiores desde jul/1994 com divisor mínimo"
                       ))
    mem_orig.adicionar(f"Coeficiente: {float(coef):.2%} | RMI", rmi_orig)

    resultado_orig = ResultadoRegra(
        nome_regra="Método Original (Lei 9.876/99 Art. 3º)",
        base_legal="Lei 9.876/99 Art. 3º",
        elegivel=True,
        rmi=rmi_orig,
        rmi_teto=rmi_orig,
        salario_beneficio=media_orig,
        coeficiente=coef,
        tempo_contribuicao=tc,
        memoria=mem_orig,
    )

    # ── MÉTODO VIDA TODA (todos os salários, sem divisor mínimo) ─────────────
    mem_vt = MemoriaCalculo()
    mem_vt.secao("MÉTODO VIDA TODA — Lei 8.213/91 Art. 29 (Tema 1.102 STF)")

    salarios_todos = extrair_e_corrigir_salarios(segurado.vinculos, der, incluir_pre_1994=True)

    if not salarios_todos:
        media_vt = Decimal("0")
        rmi_vt = Decimal("0")
        n_sel_vt = 0
    else:
        # 80% maiores SEM divisor mínimo (regra permanente Art. 29)
        n_total = len(salarios_todos)
        n_80 = max(1, round(n_total * 0.80))
        ordenados = sorted(salarios_todos, key=lambda c: c.salario_corrigido, reverse=True)
        selecionados_vt = ordenados[:n_80]
        n_sel_vt = len(selecionados_vt)
        soma = sum(c.salario_corrigido for c in selecionados_vt)
        # Sem divisor mínimo — divide pelo número de selecionados
        media_vt = (soma / Decimal(str(n_sel_vt))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        rmi_vt = rmi_com_coeficiente(media_vt, coef, teto, piso)

    mem_vt.adicionar(f"Salários no PBC (incluindo pré-1994): {len(salarios_todos)}")
    mem_vt.adicionar(f"Selecionados (80%): {n_sel_vt} — SEM divisor mínimo")
    mem_vt.adicionar("Média", media_vt,
                     fundamentacao=DispositivoLegal(
                         "Lei 8.213/91", "Art. 29 II",
                         "Regra permanente: 80% maiores de toda a vida contributiva, sem divisor mínimo"
                     ))
    mem_vt.adicionar(f"Coeficiente: {float(coef):.2%} | RMI", rmi_vt)

    resultado_vt = ResultadoRegra(
        nome_regra="Método Vida Toda (Lei 8.213/91 Art. 29 — Tema 1.102 STF)",
        base_legal="Lei 8.213/91 Art. 29 II; Tema 1.102 STF",
        elegivel=True,
        rmi=rmi_vt,
        rmi_teto=rmi_vt,
        salario_beneficio=media_vt,
        coeficiente=coef,
        tempo_contribuicao=tc,
        memoria=mem_vt,
    )

    # ── COMPARATIVO ──────────────────────────────────────────────────────────
    favoravel = rmi_vt > rmi_orig
    diferenca = (rmi_vt - rmi_orig).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    resultado_final = resultado_vt if favoravel else resultado_orig

    return {
        "metodo_original": resultado_orig,
        "metodo_vida_toda": resultado_vt,
        "favoravel": favoravel,
        "diferenca_rmi_mensal": diferenca,
        "resultado_final": resultado_final,
        "rmi_original_informada": rmi_original,
    }
