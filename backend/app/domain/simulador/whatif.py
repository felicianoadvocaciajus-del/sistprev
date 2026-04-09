"""
Simulador de Cenarios What-If.

Permite ao advogado simular rapidamente o impacto de alteracoes
nos periodos de atividade especial do segurado, comparando
o cenario original com o modificado.

Uso tipico:
  - Converter periodo normal em especial 25 e ver ganho de TC/RMI
  - Adicionar vinculo faltante e verificar se abre nova regra
  - Alterar DER para encontrar a melhor data de requerimento

Otimizado para chamadas interativas (resposta rapida).
"""
from __future__ import annotations

import copy
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from ...api.converters import segurado_from_schema, parse_date, fmt_brl
from ...api.schemas import SeguradoSchema
from ..enums import TipoAtividade
from ..models.segurado import Segurado, DadosPessoais
from ..models.vinculo import Vinculo
from ..tempo.contagem import calcular_tempo_contribuicao, calcular_carencia
from ..transicao.comparador import comparar_todas

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint spec (wired into API router separately)
# ---------------------------------------------------------------------------
ENDPOINT_SPEC = {
    "path": "/simulador/whatif",
    "method": "POST",
}

# ---------------------------------------------------------------------------
# Tipos de alteracao suportados
# ---------------------------------------------------------------------------
TIPO_CONVERTER_ESPECIAL = "CONVERTER_ESPECIAL"
TIPO_ADICIONAR_VINCULO = "ADICIONAR_VINCULO"
TIPO_ALTERAR_DER = "ALTERAR_DER"

_TIPOS_ATIVIDADE_VALIDOS = {t.value for t in TipoAtividade}


# ---------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------
def simular_cenario(
    segurado_data: Dict[str, Any],
    der: date,
    alteracoes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Simula um cenario what-if aplicando alteracoes ao segurado.

    Args:
        segurado_data: Dados do segurado serializados (formato SeguradoSchema).
        der: Data de Entrada do Requerimento original.
        alteracoes: Lista de alteracoes a aplicar. Cada item e um dict com:
            - tipo: "CONVERTER_ESPECIAL" | "ADICIONAR_VINCULO" | "ALTERAR_DER"
            - vinculo_idx: indice do vinculo a modificar (para CONVERTER_ESPECIAL)
            - tipo_atividade: novo tipo (ex: "ESPECIAL_25")
            - data_inicio / data_fim: periodo opcional da conversao (DD/MM/AAAA)
            - nova_der: nova DER (DD/MM/AAAA) para ALTERAR_DER

    Returns:
        Dict com cenario_original, cenario_modificado, diferenca, resumo
        e atrasados_estimados_5anos.

    Raises:
        ValueError: Se os dados do segurado ou alteracoes forem invalidos.
    """
    if not alteracoes:
        raise ValueError("Nenhuma alteracao informada para simulacao.")

    # --- 1. Reconstruir segurado a partir dos dados serializados -----------
    try:
        schema = SeguradoSchema.model_validate(segurado_data)
        segurado_original = segurado_from_schema(schema)
    except Exception as exc:
        raise ValueError(f"Dados do segurado invalidos: {exc}") from exc

    # --- 2. Calcular cenario original ------------------------------------
    cenario_orig = _calcular_cenario(segurado_original, der)

    # --- 3. Aplicar alteracoes em copia profunda --------------------------
    segurado_mod = copy.deepcopy(segurado_original)
    der_mod = der

    for idx, alt in enumerate(alteracoes):
        tipo = alt.get("tipo", "")
        try:
            if tipo == TIPO_CONVERTER_ESPECIAL:
                _aplicar_conversao_especial(segurado_mod, alt)
            elif tipo == TIPO_ADICIONAR_VINCULO:
                _aplicar_adicionar_vinculo(segurado_mod, alt)
            elif tipo == TIPO_ALTERAR_DER:
                der_mod = _aplicar_alterar_der(alt)
            else:
                raise ValueError(f"Tipo de alteracao desconhecido: '{tipo}'")
        except Exception as exc:
            raise ValueError(
                f"Erro na alteracao #{idx + 1} (tipo={tipo}): {exc}"
            ) from exc

    # --- 4. Calcular cenario modificado -----------------------------------
    cenario_mod = _calcular_cenario(segurado_mod, der_mod)

    # --- 5. Calcular diferencas -------------------------------------------
    diferenca = _calcular_diferenca(cenario_orig, cenario_mod)

    # --- 6. Resumo textual ------------------------------------------------
    resumo = _gerar_resumo(cenario_orig, cenario_mod, diferenca, alteracoes)

    # --- 7. Estimativa de atrasados (5 anos = 60 meses) -------------------
    rmi_diff = diferenca["rmi_diferenca"]
    # Estimativa conservadora: diferenca mensal * 60 meses * 1.15 (correcao)
    atrasados_5anos = (rmi_diff * Decimal("60") * Decimal("1.15")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "cenario_original": cenario_orig,
        "cenario_modificado": cenario_mod,
        "diferenca": diferenca,
        "resumo": resumo,
        "atrasados_estimados_5anos": atrasados_5anos,
    }


# ---------------------------------------------------------------------------
# Calculo de cenario (extraido para reuso)
# ---------------------------------------------------------------------------
def _calcular_cenario(segurado: Segurado, der: date) -> Dict[str, Any]:
    """Calcula TC, carencia e regras para um segurado em uma DER."""
    tc = calcular_tempo_contribuicao(
        vinculos=segurado.vinculos,
        der=der,
        sexo=segurado.sexo,
        incluir_especial=True,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )
    carencia = calcular_carencia(
        vinculos=segurado.vinculos,
        der=der,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )
    resultados = comparar_todas(segurado, der)

    elegiveis = [r for r in resultados if r.elegivel and r.rmi_teto > 0]
    melhor_rmi = max((r.rmi_teto for r in elegiveis), default=Decimal("0"))

    regras_elegiveis = [
        {
            "nome": r.nome_regra,
            "rmi": r.rmi_teto,
            "rmi_formatada": r.rmi_formatada,
        }
        for r in elegiveis
    ]

    return {
        "tc_dias": tc.dias_total,
        "tc_texto": tc.formatar(),
        "carencia": carencia,
        "regras_elegiveis": regras_elegiveis,
        "melhor_rmi": melhor_rmi,
    }


# ---------------------------------------------------------------------------
# Aplicacao de alteracoes
# ---------------------------------------------------------------------------
def _aplicar_conversao_especial(
    segurado: Segurado,
    alt: Dict[str, Any],
) -> None:
    """Converte um vinculo (ou parte dele) para atividade especial."""
    vinculo_idx = alt.get("vinculo_idx")
    if vinculo_idx is None:
        raise ValueError("vinculo_idx e obrigatorio para CONVERTER_ESPECIAL.")

    if vinculo_idx < 0 or vinculo_idx >= len(segurado.vinculos):
        raise ValueError(
            f"vinculo_idx={vinculo_idx} fora do intervalo "
            f"(0..{len(segurado.vinculos) - 1})."
        )

    tipo_ativ_str = alt.get("tipo_atividade", "ESPECIAL_25")
    if tipo_ativ_str not in _TIPOS_ATIVIDADE_VALIDOS:
        raise ValueError(
            f"tipo_atividade '{tipo_ativ_str}' invalido. "
            f"Valores aceitos: {sorted(_TIPOS_ATIVIDADE_VALIDOS)}"
        )
    novo_tipo = TipoAtividade(tipo_ativ_str)

    vinculo = segurado.vinculos[vinculo_idx]

    # Se data_inicio/data_fim foram informados, precisamos dividir o vinculo
    dt_inicio_str = alt.get("data_inicio")
    dt_fim_str = alt.get("data_fim")

    if dt_inicio_str or dt_fim_str:
        _converter_parcial(segurado, vinculo_idx, novo_tipo, dt_inicio_str, dt_fim_str)
    else:
        # Conversao total do vinculo
        vinculo.tipo_atividade = novo_tipo


def _converter_parcial(
    segurado: Segurado,
    vinculo_idx: int,
    novo_tipo: TipoAtividade,
    dt_inicio_str: Optional[str],
    dt_fim_str: Optional[str],
) -> None:
    """
    Converte apenas um sub-periodo do vinculo para especial.

    Divide o vinculo original em ate 3 partes:
      [antes_normal] [periodo_especial] [depois_normal]
    """
    vinculo_orig = segurado.vinculos[vinculo_idx]
    v_inicio = vinculo_orig.data_inicio
    v_fim = vinculo_orig.data_fim_efetiva

    conv_inicio = parse_date(dt_inicio_str) if dt_inicio_str else v_inicio
    conv_fim = parse_date(dt_fim_str) if dt_fim_str else v_fim

    # Validar limites
    conv_inicio = max(conv_inicio, v_inicio)
    conv_fim = min(conv_fim, v_fim)

    if conv_inicio > conv_fim:
        raise ValueError(
            f"Periodo de conversao invalido: "
            f"{conv_inicio.strftime('%d/%m/%Y')} a {conv_fim.strftime('%d/%m/%Y')}"
        )

    novos_vinculos: List[Vinculo] = []

    # Parte antes (normal)
    if conv_inicio > v_inicio:
        antes = copy.deepcopy(vinculo_orig)
        from datetime import timedelta as _td
        antes.data_fim = conv_inicio - _td(days=1)
        antes.contribuicoes = [
            c for c in antes.contribuicoes
            if date(c.competencia.year, c.competencia.month, 1) < conv_inicio
        ]
        novos_vinculos.append(antes)

    # Parte especial (convertida)
    especial = copy.deepcopy(vinculo_orig)
    especial.data_inicio = conv_inicio
    especial.data_fim = conv_fim
    especial.tipo_atividade = novo_tipo
    especial.contribuicoes = [
        c for c in especial.contribuicoes
        if conv_inicio <= date(c.competencia.year, c.competencia.month, 1) <= conv_fim
    ]
    novos_vinculos.append(especial)

    # Parte depois (normal)
    from datetime import timedelta
    if conv_fim < v_fim:
        depois = copy.deepcopy(vinculo_orig)
        depois.data_inicio = conv_fim + timedelta(days=1)
        depois.data_fim = vinculo_orig.data_fim  # preservar None se era aberto
        depois.contribuicoes = [
            c for c in depois.contribuicoes
            if date(c.competencia.year, c.competencia.month, 1) > conv_fim
        ]
        novos_vinculos.append(depois)

    # Substituir o vinculo original pelos novos
    segurado.vinculos[vinculo_idx:vinculo_idx + 1] = novos_vinculos


def _aplicar_adicionar_vinculo(
    segurado: Segurado,
    alt: Dict[str, Any],
) -> None:
    """Adiciona um novo vinculo ao segurado."""
    from ..enums import TipoVinculo, RegimePrevidenciario, OrigemDado

    data_inicio_str = alt.get("data_inicio")
    data_fim_str = alt.get("data_fim")

    if not data_inicio_str:
        raise ValueError("data_inicio e obrigatorio para ADICIONAR_VINCULO.")

    tipo_ativ_str = alt.get("tipo_atividade", "NORMAL")
    if tipo_ativ_str not in _TIPOS_ATIVIDADE_VALIDOS:
        raise ValueError(f"tipo_atividade '{tipo_ativ_str}' invalido.")

    tipo_vinculo_str = alt.get("tipo_vinculo", "EMPREGADO")
    try:
        tipo_vinculo = TipoVinculo[tipo_vinculo_str]
    except KeyError:
        raise ValueError(f"tipo_vinculo '{tipo_vinculo_str}' invalido.")

    novo = Vinculo(
        tipo_vinculo=tipo_vinculo,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade(tipo_ativ_str),
        empregador_nome=alt.get("empregador_nome", "Vinculo simulado"),
        data_inicio=parse_date(data_inicio_str),
        data_fim=parse_date(data_fim_str) if data_fim_str else None,
        origem=OrigemDado.MANUAL,
    )
    segurado.adicionar_vinculo(novo)


def _aplicar_alterar_der(alt: Dict[str, Any]) -> date:
    """Retorna a nova DER a partir da alteracao."""
    nova_der_str = alt.get("nova_der")
    if not nova_der_str:
        raise ValueError("nova_der e obrigatorio para ALTERAR_DER.")
    return parse_date(nova_der_str)


# ---------------------------------------------------------------------------
# Calculo de diferencas
# ---------------------------------------------------------------------------
def _calcular_diferenca(
    orig: Dict[str, Any],
    mod: Dict[str, Any],
) -> Dict[str, Any]:
    """Calcula as diferencas entre dois cenarios."""
    tc_ganho = mod["tc_dias"] - orig["tc_dias"]

    # Formatar ganho de TC em texto legivel
    ganho_anos = abs(tc_ganho) // 365
    ganho_meses = (abs(tc_ganho) % 365) // 30
    ganho_dias = (abs(tc_ganho) % 365) % 30
    sinal = "+" if tc_ganho >= 0 else "-"
    tc_texto_ganho = f"{sinal}{ganho_anos}a {ganho_meses}m {ganho_dias}d"

    rmi_diff = mod["melhor_rmi"] - orig["melhor_rmi"]

    nomes_orig = {r["nome"] for r in orig["regras_elegiveis"]}
    nomes_mod = {r["nome"] for r in mod["regras_elegiveis"]}

    return {
        "tc_dias_ganho": tc_ganho,
        "tc_texto_ganho": tc_texto_ganho,
        "rmi_diferenca": rmi_diff,
        "rmi_diferenca_formatada": fmt_brl(abs(rmi_diff)),
        "novas_regras_elegiveis": sorted(nomes_mod - nomes_orig),
        "regras_perdidas": sorted(nomes_orig - nomes_mod),
    }


# ---------------------------------------------------------------------------
# Resumo textual
# ---------------------------------------------------------------------------
def _gerar_resumo(
    orig: Dict[str, Any],
    mod: Dict[str, Any],
    diferenca: Dict[str, Any],
    alteracoes: List[Dict[str, Any]],
) -> str:
    """Gera um resumo legivel das diferencas entre cenarios."""
    partes: List[str] = []

    # Descrever as alteracoes aplicadas
    desc_alts = _descrever_alteracoes(alteracoes)
    if desc_alts:
        partes.append(desc_alts)

    # TC
    tc_ganho = diferenca["tc_dias_ganho"]
    if tc_ganho > 0:
        partes.append(
            f"TC sobe de {orig['tc_texto']} para {mod['tc_texto']} "
            f"({diferenca['tc_texto_ganho']})"
        )
    elif tc_ganho < 0:
        partes.append(
            f"TC cai de {orig['tc_texto']} para {mod['tc_texto']} "
            f"({diferenca['tc_texto_ganho']})"
        )

    # RMI
    rmi_diff = diferenca["rmi_diferenca"]
    if rmi_diff > 0:
        partes.append(
            f"RMI sobe de {fmt_brl(orig['melhor_rmi'])} "
            f"para {fmt_brl(mod['melhor_rmi'])} "
            f"(+{diferenca['rmi_diferenca_formatada']})"
        )
    elif rmi_diff < 0:
        partes.append(
            f"RMI cai de {fmt_brl(orig['melhor_rmi'])} "
            f"para {fmt_brl(mod['melhor_rmi'])} "
            f"(-{diferenca['rmi_diferenca_formatada']})"
        )

    # Novas regras
    novas = diferenca["novas_regras_elegiveis"]
    if novas:
        partes.append(f"Novas regras elegiveis: {', '.join(novas)}")

    perdidas = diferenca["regras_perdidas"]
    if perdidas:
        partes.append(f"Regras que deixam de ser elegiveis: {', '.join(perdidas)}")

    if not partes:
        return "Nenhuma diferenca significativa encontrada."

    return ". ".join(partes) + "."


def _descrever_alteracoes(alteracoes: List[Dict[str, Any]]) -> str:
    """Gera descricao resumida das alteracoes aplicadas."""
    descricoes: List[str] = []
    for alt in alteracoes:
        tipo = alt.get("tipo", "")
        if tipo == TIPO_CONVERTER_ESPECIAL:
            ativ = alt.get("tipo_atividade", "ESPECIAL_25")
            periodo = ""
            if alt.get("data_inicio") and alt.get("data_fim"):
                periodo = f" ({alt['data_inicio']} a {alt['data_fim']})"
            elif alt.get("data_inicio"):
                periodo = f" (a partir de {alt['data_inicio']})"
            descricoes.append(f"Converter vinculo #{alt.get('vinculo_idx', '?')} para {ativ}{periodo}")
        elif tipo == TIPO_ADICIONAR_VINCULO:
            periodo = alt.get("data_inicio", "?")
            if alt.get("data_fim"):
                periodo += f" a {alt['data_fim']}"
            descricoes.append(f"Adicionar vinculo ({periodo})")
        elif tipo == TIPO_ALTERAR_DER:
            descricoes.append(f"Alterar DER para {alt.get('nova_der', '?')}")

    if not descricoes:
        return ""
    return "Ao " + descricoes[0].lower() + (
        " e " + ", ".join(d.lower() for d in descricoes[1:])
        if len(descricoes) > 1 else ""
    )
