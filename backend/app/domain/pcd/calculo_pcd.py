"""
Aposentadoria da Pessoa com Deficiência — LC 142/2013.

Modalidades:
  1. Por Tempo de Contribuição: 25/29/33(H) ou 20/24/28(M) conforme grau
  2. Por Idade: 60(H)/55(M) com 15 anos como PcD

Cálculo:
  - TC PcD: RMI = 100% do SB (média 80% maiores)
  - Idade PcD: RMI = 70% + 1% por ano de TC
  - Fator previdenciário só se > 1.0

EC 103/2019 Art. 22: regras preservadas integralmente.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Any, Optional


class GrauDeficiencia(str, Enum):
    GRAVE = "GRAVE"
    MODERADA = "MODERADA"
    LEVE = "LEVE"


@dataclass
class PeriodoPcD:
    """Período com determinado grau de deficiência."""
    grau: GrauDeficiencia
    data_inicio: date
    data_fim: Optional[date] = None
    descricao: str = ""


# Tempo exigido por grau (anos)
TEMPO_EXIGIDO = {
    GrauDeficiencia.GRAVE: {"masculino": 25, "feminino": 20},
    GrauDeficiencia.MODERADA: {"masculino": 29, "feminino": 24},
    GrauDeficiencia.LEVE: {"masculino": 33, "feminino": 28},
}

# Tempo sem deficiência (para conversão)
TEMPO_COMUM = {"masculino": 35, "feminino": 30}

# Idade PcD
IDADE_PCD = {"masculino": 60, "feminino": 55}

# Carência
CARENCIA_PCD = 180  # meses


def _fator_conversao(grau_origem: GrauDeficiencia, grau_destino: GrauDeficiencia, sexo: str) -> float:
    """Calcula fator de conversão entre graus de deficiência."""
    tempo_origem = TEMPO_EXIGIDO[grau_origem][sexo]
    tempo_destino = TEMPO_EXIGIDO[grau_destino][sexo]
    return round(tempo_destino / tempo_origem, 4)


def _fator_conversao_comum_para_pcd(grau_destino: GrauDeficiencia, sexo: str) -> float:
    """Fator para converter tempo sem deficiência para tempo PcD."""
    tempo_comum = TEMPO_COMUM[sexo]
    tempo_destino = TEMPO_EXIGIDO[grau_destino][sexo]
    return round(tempo_destino / tempo_comum, 4)


def _fator_conversao_pcd_para_comum(grau_origem: GrauDeficiencia, sexo: str) -> float:
    """Fator para converter tempo PcD para tempo comum."""
    tempo_origem = TEMPO_EXIGIDO[grau_origem][sexo]
    tempo_comum = TEMPO_COMUM[sexo]
    return round(tempo_comum / tempo_origem, 4)


def calcular_tempo_convertido(
    periodos_pcd: List[PeriodoPcD],
    tempo_comum_dias: int,
    grau_destino: GrauDeficiencia,
    sexo: str,
    data_referencia: date,
) -> Dict[str, Any]:
    """
    Converte todos os períodos para o grau de destino e soma.

    Returns:
        dict with total_dias_convertidos, detalhamento per período, tempo_exigido_dias
    """
    detalhamento = []
    total_convertido = 0

    for p in periodos_pcd:
        fim = p.data_fim or data_referencia
        dias = (fim - p.data_inicio).days
        if dias <= 0:
            continue

        if p.grau == grau_destino:
            fator = 1.0
        else:
            fator = _fator_conversao(p.grau, grau_destino, sexo)

        dias_convertidos = int(dias * fator)
        total_convertido += dias_convertidos

        detalhamento.append({
            "periodo": f"{p.data_inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
            "grau_original": p.grau.value,
            "dias_originais": dias,
            "fator": fator,
            "dias_convertidos": dias_convertidos,
        })

    # Converter tempo comum (sem deficiência)
    if tempo_comum_dias > 0:
        fator_comum = _fator_conversao_comum_para_pcd(grau_destino, sexo)
        dias_conv_comum = int(tempo_comum_dias * fator_comum)
        total_convertido += dias_conv_comum
        detalhamento.append({
            "periodo": "Tempo sem deficiência",
            "grau_original": "SEM DEFICIÊNCIA",
            "dias_originais": tempo_comum_dias,
            "fator": fator_comum,
            "dias_convertidos": dias_conv_comum,
        })

    tempo_exigido_anos = TEMPO_EXIGIDO[grau_destino][sexo]
    tempo_exigido_dias = tempo_exigido_anos * 365

    anos = total_convertido // 365
    meses = (total_convertido % 365) // 30
    dias = total_convertido % 30

    return {
        "grau_destino": grau_destino.value,
        "total_dias_convertidos": total_convertido,
        "anos": anos,
        "meses": meses,
        "dias": dias,
        "texto": f"{anos} anos, {meses} meses e {dias} dias",
        "tempo_exigido_anos": tempo_exigido_anos,
        "tempo_exigido_dias": tempo_exigido_dias,
        "cumprido": total_convertido >= tempo_exigido_dias,
        "faltam_dias": max(0, tempo_exigido_dias - total_convertido),
        "detalhamento": detalhamento,
    }


def calcular_aposentadoria_pcd(
    sexo: str,
    data_nascimento: date,
    periodos_pcd: List[PeriodoPcD],
    tempo_comum_dias: int,
    carencia_meses: int,
    salarios_contribuicao: List[Decimal],
    data_referencia: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Calcula todas as possibilidades de aposentadoria PcD.

    Returns:
        dict com análise de cada modalidade e melhor opção
    """
    der = data_referencia or date.today()
    idade_anos = (der - data_nascimento).days // 365

    resultado = {
        "data_referencia": der.strftime("%d/%m/%Y"),
        "sexo": sexo,
        "idade": idade_anos,
        "carencia_meses": carencia_meses,
        "carencia_exigida": CARENCIA_PCD,
        "carencia_ok": carencia_meses >= CARENCIA_PCD,
        "modalidades": [],
        "melhor_opcao": None,
        "tabela_conversao": _gerar_tabela_conversao(sexo),
    }

    # Calcular SB (média 80% maiores)
    sb = _calcular_salario_beneficio(salarios_contribuicao)
    resultado["salario_beneficio"] = str(sb)

    # ═══════════════════════════════════════════════════════════════
    # MODALIDADE 1: POR TEMPO DE CONTRIBUIÇÃO
    # ═══════════════════════════════════════════════════════════════

    for grau in GrauDeficiencia:
        tc_conv = calcular_tempo_convertido(
            periodos_pcd, tempo_comum_dias, grau, sexo, der
        )

        rmi = sb  # 100% do SB

        modalidade = {
            "tipo": "TEMPO DE CONTRIBUIÇÃO",
            "grau": grau.value,
            "tempo_exigido": f"{TEMPO_EXIGIDO[grau][sexo]} anos",
            "tempo_atual": tc_conv["texto"],
            "cumprido": tc_conv["cumprido"],
            "carencia_ok": resultado["carencia_ok"],
            "elegivel": tc_conv["cumprido"] and resultado["carencia_ok"],
            "rmi": str(rmi) if tc_conv["cumprido"] else None,
            "rmi_formatada": f"R$ {rmi:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tc_conv["cumprido"] else "—",
            "calculo": "100% do Salário de Benefício (média dos 80% maiores SC)",
            "fator_previdenciario": "Não se aplica (somente se > 1.0)",
            "faltam": tc_conv["faltam_dias"],
            "detalhamento_conversao": tc_conv["detalhamento"],
            "fundamentacao": f"Art. 3º, I, LC 142/2013 — Deficiência {grau.value}: {TEMPO_EXIGIDO[grau][sexo]} anos ({sexo})",
            "base_legal": "LC 142/2013, Art. 3º, I; EC 103/2019, Art. 22",
        }
        resultado["modalidades"].append(modalidade)

    # ═══════════════════════════════════════════════════════════════
    # MODALIDADE 2: POR IDADE
    # ═══════════════════════════════════════════════════════════════

    idade_exigida = IDADE_PCD[sexo]
    total_pcd_dias = sum((((p.data_fim or der) - p.data_inicio).days) for p in periodos_pcd if (p.data_fim or der) > p.data_inicio)
    tc_pcd_anos = total_pcd_dias // 365

    # RMI por idade: 70% + 1% por ano de TC (max 100%)
    coef = min(100, 70 + carencia_meses // 12)
    rmi_idade = (sb * Decimal(str(coef)) / Decimal("100")).quantize(Decimal("0.01"))

    modalidade_idade = {
        "tipo": "IDADE",
        "grau": "QUALQUER",
        "idade_exigida": idade_exigida,
        "idade_atual": idade_anos,
        "idade_ok": idade_anos >= idade_exigida,
        "tc_como_pcd": f"{tc_pcd_anos} anos",
        "tc_exigido_pcd": "15 anos",
        "tc_pcd_ok": tc_pcd_anos >= 15,
        "carencia_ok": resultado["carencia_ok"],
        "elegivel": idade_anos >= idade_exigida and tc_pcd_anos >= 15 and resultado["carencia_ok"],
        "coeficiente": f"{coef}%",
        "rmi": str(rmi_idade) if idade_anos >= idade_exigida else None,
        "rmi_formatada": f"R$ {rmi_idade:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if idade_anos >= idade_exigida else "—",
        "calculo": f"SB × {coef}% (70% + 1% por ano de contribuição)",
        "fator_previdenciario": "Não se aplica",
        "fundamentacao": f"Art. 3º, IV, LC 142/2013 — {idade_exigida} anos de idade ({sexo}) + 15 anos como PcD",
        "base_legal": "LC 142/2013, Art. 3º, IV; EC 103/2019, Art. 22",
    }
    resultado["modalidades"].append(modalidade_idade)

    # ═══════════════════════════════════════════════════════════════
    # MELHOR OPÇÃO
    # ═══════════════════════════════════════════════════════════════

    elegiveis = [m for m in resultado["modalidades"] if m["elegivel"]]
    if elegiveis:
        melhor = max(elegiveis, key=lambda m: Decimal(m["rmi"]) if m["rmi"] else Decimal("0"))
        resultado["melhor_opcao"] = {
            "tipo": melhor["tipo"],
            "grau": melhor["grau"],
            "rmi": melhor["rmi"],
            "rmi_formatada": melhor["rmi_formatada"],
            "fundamentacao": melhor["fundamentacao"],
        }
    else:
        # Projetar quando será elegível
        faltam_list = []
        for m in resultado["modalidades"]:
            if m.get("faltam") and m["faltam"] > 0:
                faltam_list.append({
                    "modalidade": f"{m['tipo']} - {m['grau']}",
                    "faltam_dias": m["faltam"],
                    "faltam_texto": f"{m['faltam'] // 365} anos e {(m['faltam'] % 365) // 30} meses",
                })
        if faltam_list:
            mais_proximo = min(faltam_list, key=lambda x: x["faltam_dias"])
            resultado["melhor_opcao"] = {
                "tipo": "PROJEÇÃO",
                "modalidade_mais_proxima": mais_proximo["modalidade"],
                "faltam": mais_proximo["faltam_texto"],
                "mensagem": f"Modalidade mais próxima: {mais_proximo['modalidade']} — faltam {mais_proximo['faltam_texto']}.",
            }

    return resultado


def _calcular_salario_beneficio(salarios: List[Decimal]) -> Decimal:
    """Média dos 80% maiores salários de contribuição."""
    if not salarios:
        return Decimal("1412.00")  # Salário mínimo 2024

    ordenados = sorted(salarios, reverse=True)
    n80 = max(1, int(len(ordenados) * 0.8))
    maiores = ordenados[:n80]
    media = sum(maiores) / Decimal(str(len(maiores)))
    return media.quantize(Decimal("0.01"))


def _gerar_tabela_conversao(sexo: str) -> List[Dict]:
    """Gera tabela de fatores de conversão para exibição."""
    tabela = []
    origens = list(GrauDeficiencia) + ["SEM_DEFICIENCIA"]
    destinos = list(GrauDeficiencia)

    for origem in origens:
        for destino in destinos:
            if isinstance(origem, GrauDeficiencia) and isinstance(destino, GrauDeficiencia):
                if origem == destino:
                    fator = 1.0
                else:
                    fator = _fator_conversao(origem, destino, sexo)
                nome_orig = origem.value
            else:
                fator = _fator_conversao_comum_para_pcd(destino, sexo)
                nome_orig = "SEM DEFICIÊNCIA"

            tabela.append({
                "origem": nome_orig,
                "destino": destino.value,
                "fator": round(fator, 4),
                "tempo_origem": TEMPO_EXIGIDO[origem][sexo] if isinstance(origem, GrauDeficiencia) else TEMPO_COMUM[sexo],
                "tempo_destino": TEMPO_EXIGIDO[destino][sexo],
            })

    return tabela
