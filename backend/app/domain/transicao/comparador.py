"""
Comparador automatico: roda as regras CORRETAS conforme o marco temporal.

PRINCIPIO FUNDAMENTAL: tempus regit actum
  - DER < 13/11/2019 → regras PRE-REFORMA (TC+FP, 85/95, Idade pre)
  - DER >= 13/11/2019 → regras de TRANSICAO EC 103 + Direito Adquirido + Permanente

NUNCA aplicar regra fora de seu marco temporal de vigencia.
"""
from __future__ import annotations
from datetime import date
from typing import List, Optional
import logging

from .regras import (
    RegraPonitosProgressivos,
    RegraIdadeProgressiva,
    RegraPedagio50,
    RegraPedagio100,
    RegraDireitoAdquirido,
)
from .regras_pre_reforma import (
    RegraTCComFator,
    Regra85_95,
    RegraIdadePreReforma,
)
from .base import RegraTransicao
from ..beneficios.aposentadoria_idade import CalculadoraAposentadoriaIdade
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra
from ..constantes import DatasCorte

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# REGRAS ORGANIZADAS POR MARCO TEMPORAL
# ──────────────────────────────────────────────────────────────────────────────

# Regras para DER ANTES de 13/11/2019 (pre-reforma)
REGRAS_PRE_REFORMA: List[RegraTransicao] = [
    RegraTCComFator(),       # TC puro + FP obrigatorio
    Regra85_95(),            # 85/95 → afasta FP
    RegraIdadePreReforma(),  # Idade 65H/60M + 180 carencia
]

# Regras para DER A PARTIR de 13/11/2019 (pos-reforma)
REGRAS_POS_REFORMA: List[RegraTransicao] = [
    RegraDireitoAdquirido(),      # Quem completou antes da reforma
    RegraPonitosProgressivos(),    # Art. 15
    RegraIdadeProgressiva(),       # Art. 16
    RegraPedagio50(),              # Art. 17
    RegraPedagio100(),             # Art. 20
]


def comparar_todas(segurado: Segurado, der: date) -> List[ResultadoRegra]:
    """
    Executa as regras CORRETAS conforme a DER informada.

    Se DER < 13/11/2019 → roda APENAS regras pre-reforma.
    Se DER >= 13/11/2019 → roda regras de transicao EC 103 + Direito Adquirido + Permanente.

    Retorna lista completa (elegiveis e nao-elegiveis), ordenada da maior RMI para a menor.
    """
    resultados: List[ResultadoRegra] = []
    is_pre_reforma = der < DatasCorte.EC_103_2019

    if is_pre_reforma:
        _logger.info(f"DER {der} < 13/11/2019 → aplicando regras PRE-REFORMA")
        regras = REGRAS_PRE_REFORMA
    else:
        _logger.info(f"DER {der} >= 13/11/2019 → aplicando regras EC 103/2019")
        regras = REGRAS_POS_REFORMA

    for regra in regras:
        try:
            resultado = regra.calcular(segurado, der)
            resultados.append(resultado)
        except Exception as e:
            _logger.warning(f"Erro ao calcular regra {regra.nome}: {e}")
            resultados.append(ResultadoRegra(
                nome_regra=regra.nome,
                base_legal=regra.base_legal,
                elegivel=False,
                avisos=[f"Erro no calculo: {str(e)}"],
            ))

    # Regra permanente de aposentadoria por idade
    # Pre-reforma: ja incluida em REGRAS_PRE_REFORMA (RegraIdadePreReforma)
    # Pos-reforma: calcular via CalculadoraAposentadoriaIdade
    if not is_pre_reforma:
        try:
            calc_idade = CalculadoraAposentadoriaIdade()
            r_idade = calc_idade.calcular_rmi(segurado, der)
            req_idade = calc_idade.verificar_requisitos(segurado, der)
            r_idade.elegivel = req_idade.elegivel
            r_idade.nome_regra = "Aposentadoria por Idade (Regra Permanente EC 103)"
            r_idade.base_legal = "EC 103/2019 Art. 19; Lei 8.213/91 Art. 48"
            resultados.append(r_idade)
        except Exception as e:
            _logger.warning(f"Erro ao calcular aposentadoria por idade permanente: {e}")

    # Ordenar: elegiveis primeiro (maior RMI), depois nao-elegiveis (menor faltam_dias)
    elegiveis = sorted(
        [r for r in resultados if r.elegivel],
        key=lambda r: r.rmi_teto, reverse=True
    )
    nao_elegiveis = sorted(
        [r for r in resultados if not r.elegivel],
        key=lambda r: r.faltam_dias
    )

    return elegiveis + nao_elegiveis


def melhor_regra(segurado: Segurado, der: date) -> Optional[ResultadoRegra]:
    """Retorna a regra mais vantajosa (maior RMI entre as elegiveis)."""
    todos = comparar_todas(segurado, der)
    elegiveis = [r for r in todos if r.elegivel and r.rmi_teto > 0]
    if not elegiveis:
        return None
    return elegiveis[0]
