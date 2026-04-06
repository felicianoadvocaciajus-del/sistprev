"""
Revisão do Teto — EC 20/98 e EC 41/03.

Beneficiários cujo salário de benefício era maior que o teto vigente na concessão
têm direito à readequação quando o teto foi elevado pelas emendas constitucionais.

EC 20/98: teto elevado para R$ 1.200,00 a partir de 12/1998.
EC 41/03: teto elevado para R$ 2.400,00 a partir de 01/2004.

Prazo prescricional: 5 anos (a partir da data em que a parcela se tornou exigível).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from ..domain.models.resultado import MemoriaCalculo, DispositivoLegal
from ..domain.indices.teto_previdenciario import teto_em
from ..domain.indices.correcao_monetaria import corrigir_salario
from ..domain.constantes import DatasCorte, TETO_EC20_98, TETO_EC41_03
from ..domain.models.contribuicao import Competencia


def calcular_revisao_teto(
    dib: date,
    rmi_original: Decimal,
    salario_beneficio_original: Decimal,
    der_revisao: date,
) -> dict:
    """
    Calcula a revisão do teto conforme EC 20/98 e/ou EC 41/03.

    dib: Data de Início do Benefício (data de concessão original)
    rmi_original: RMI original concedida (já limitada ao teto vigente)
    salario_beneficio_original: SB calculado na concessão (pode ser maior que o teto)
    der_revisao: data da revisão (hoje ou data do requerimento)

    Retorna dict com a análise de cada EC e as diferenças mensais.
    """
    mem = MemoriaCalculo()
    mem.secao("REVISÃO DO TETO — EC 20/98 e EC 41/03")

    resultado = {
        "dib": dib,
        "rmi_original": rmi_original,
        "sb_original": salario_beneficio_original,
        "ec20_aplicavel": False,
        "ec41_aplicavel": False,
        "rmi_pos_ec20": None,
        "rmi_pos_ec41": None,
        "memoria": mem,
    }

    # ── EC 20/98 ─────────────────────────────────────────────────────────────
    # Aplicável quando: DIB anterior a 12/1998 e SB original > teto da época
    if dib < DatasCorte.EC_20_98:
        teto_na_concessao = teto_em(dib.year, dib.month)
        if salario_beneficio_original > teto_na_concessao:
            resultado["ec20_aplicavel"] = True
            # Nova RMI = min(SB_original, novo_teto_EC20) × reajustes posteriores
            nova_rmi_ec20 = min(salario_beneficio_original, TETO_EC20_98)
            # Reajustar pela variação do INPC entre o DIB e a vigência da EC20
            # (a RMI deve ser igual ao SB limitado ao novo teto, na data da EC20)
            resultado["rmi_pos_ec20"] = nova_rmi_ec20.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            mem.adicionar(
                f"EC 20/98: SB original ({salario_beneficio_original}) > teto concessão ({teto_na_concessao})",
                nova_rmi_ec20,
                fundamentacao=DispositivoLegal(
                    "EC 20/98", "Art. 14",
                    "Adequação do limite máximo dos benefícios previdenciários"
                )
            )
        else:
            mem.adicionar(
                f"EC 20/98: não aplicável — SB ({salario_beneficio_original}) ≤ teto ({teto_na_concessao})"
            )
    else:
        mem.adicionar("EC 20/98: não aplicável — DIB posterior a 12/1998")

    # ── EC 41/03 ─────────────────────────────────────────────────────────────
    # Aplicável quando: DIB anterior a 01/2004 e SB original > teto da época
    if dib < DatasCorte.EC_41_VIGENCIA_TETO:
        teto_na_concessao_41 = teto_em(dib.year, dib.month)
        if salario_beneficio_original > teto_na_concessao_41:
            resultado["ec41_aplicavel"] = True
            nova_rmi_ec41 = min(salario_beneficio_original, TETO_EC41_03)
            resultado["rmi_pos_ec41"] = nova_rmi_ec41.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            mem.adicionar(
                f"EC 41/03: SB original ({salario_beneficio_original}) > teto concessão ({teto_na_concessao_41})",
                nova_rmi_ec41,
                fundamentacao=DispositivoLegal(
                    "EC 41/03", "Art. 5º",
                    "Reajustamento do limite máximo dos benefícios do RGPS"
                )
            )
        else:
            mem.adicionar(
                f"EC 41/03: não aplicável — SB ({salario_beneficio_original}) ≤ teto ({teto_na_concessao_41})"
            )
    else:
        mem.adicionar("EC 41/03: não aplicável — DIB posterior a 01/2004")

    # Diferença mensal estimada
    rmi_revisada = resultado.get("rmi_pos_ec41") or resultado.get("rmi_pos_ec20") or rmi_original
    resultado["diferenca_mensal"] = (rmi_revisada - rmi_original).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    resultado["rmi_revisada"] = rmi_revisada

    return resultado
