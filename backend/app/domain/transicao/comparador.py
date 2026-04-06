"""
Comparador automático: roda todas as 5 regras de transição e elege a mais vantajosa.
"""
from __future__ import annotations
from datetime import date
from typing import List, Optional

from .regras import (
    RegraPonitosProgressivos,
    RegraIdadeProgressiva,
    RegraPedagio50,
    RegraPedagio100,
    RegraDireitoAdquirido,
)
from .base import RegraTransicao
from ..beneficios.aposentadoria_idade import CalculadoraAposentadoriaIdade
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra


TODAS_AS_REGRAS: List[RegraTransicao] = [
    RegraDireitoAdquirido(),
    RegraPonitosProgressivos(),
    RegraIdadeProgressiva(),
    RegraPedagio50(),
    RegraPedagio100(),
]


def comparar_todas(segurado: Segurado, der: date) -> List[ResultadoRegra]:
    """
    Executa todas as 5 regras de transição + regra permanente de aposentadoria por idade.
    Retorna lista completa (elegíveis e não-elegíveis), ordenada da maior RMI para a menor.
    """
    resultados: List[ResultadoRegra] = []

    for regra in TODAS_AS_REGRAS:
        try:
            resultado = regra.calcular(segurado, der)
            resultados.append(resultado)
        except Exception as e:
            resultados.append(ResultadoRegra(
                nome_regra=regra.nome,
                base_legal=regra.base_legal,
                elegivel=False,
                avisos=[f"Erro no cálculo: {str(e)}"],
            ))

    # Também calcula a aposentadoria por idade (regra permanente)
    try:
        calc_idade = CalculadoraAposentadoriaIdade()
        r_idade = calc_idade.calcular_rmi(segurado, der)
        req_idade = calc_idade.verificar_requisitos(segurado, der)
        r_idade.elegivel = req_idade.elegivel
        r_idade.nome_regra = "Aposentadoria por Idade (Regra Permanente)"
        r_idade.base_legal = "EC 103/2019 Art. 19; Lei 8.213/91 Art. 48"
        resultados.append(r_idade)
    except Exception as e:
        pass

    # Ordenar: elegíveis primeiro (maior RMI), depois não-elegíveis (menor faltam_dias)
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
    """Retorna a regra mais vantajosa (maior RMI entre as elegíveis)."""
    todos = comparar_todas(segurado, der)
    elegiveis = [r for r in todos if r.elegivel and r.rmi_teto > 0]
    if not elegiveis:
        return None
    return elegiveis[0]
