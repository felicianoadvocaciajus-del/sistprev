"""
Detetive Previdenciario - Motor de Cruzamento Automatico

Analisa dados de multiplos documentos (CNIS, CTPS, PPP, LTCAT, Carta de Concessao)
para identificar oportunidades prevvidenciarias para o cliente.

Cada oportunidade detectada inclui tipo, descricao, nivel de confianca,
acao recomendada, documentos necessarios, fundamentacao legal e impacto estimado.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DATA_LIMITE_CONVERSAO = date(2019, 11, 13)  # EC 103/2019

CARGOS_ESPECIAIS: Dict[str, str] = {
    "soldador": "Agente nocivo: fumos metalicos (soldagem)",
    "enfermeiro": "Agente nocivo: agentes biologicos",
    "enfermeira": "Agente nocivo: agentes biologicos",
    "tecnico de enfermagem": "Agente nocivo: agentes biologicos",
    "tecnica de enfermagem": "Agente nocivo: agentes biologicos",
    "auxiliar de enfermagem": "Agente nocivo: agentes biologicos",
    "medico": "Agente nocivo: agentes biologicos",
    "medica": "Agente nocivo: agentes biologicos",
    "dentista": "Agente nocivo: agentes biologicos",
    "eletricista": "Agente nocivo: eletricidade acima de 250V",
    "torneiro mecanico": "Agente nocivo: ruido / oleo mineral",
    "frentista": "Agente nocivo: hidrocarbonetos",
    "motorista de caminhao": "Agente nocivo: vibracoes / ruido",
    "operador de maquinas": "Agente nocivo: ruido / vibracoes",
    "vigilante": "Agente nocivo: periculosidade (porte de arma)",
    "vigia armado": "Agente nocivo: periculosidade (porte de arma)",
    "minerador": "Agente nocivo: poeiras minerais",
    "pintor industrial": "Agente nocivo: solventes organicos",
    "quimico": "Agente nocivo: agentes quimicos diversos",
    "laboratorista": "Agente nocivo: agentes quimicos / biologicos",
    "bombeiro": "Agente nocivo: periculosidade",
    "radiologista": "Agente nocivo: radiacoes ionizantes",
    "tecnico em radiologia": "Agente nocivo: radiacoes ionizantes",
    "operador de raio-x": "Agente nocivo: radiacoes ionizantes",
    "mecanico": "Agente nocivo: ruido / oleo mineral / graxas",
    "caldeireiro": "Agente nocivo: ruido / calor",
    "funileiro": "Agente nocivo: ruido / poeiras metalicas",
    "galvanoplasta": "Agente nocivo: cromo / niquel",
    "serralheiro": "Agente nocivo: ruido / poeiras metalicas",
}

EMPRESAS_ESPECIAIS_KEYWORDS: List[str] = [
    "metalurgica",
    "metalurgia",
    "siderurgica",
    "siderurgia",
    "quimica",
    "petroquimica",
    "mineracao",
    "mineradora",
    "fundição",
    "fundicao",
    "galvanoplastia",
    "curtume",
    "frigorific",
    "hospital",
    "clinica",
    "laboratorio",
    "usina",
    "termoeletrica",
    "nuclear",
    "radiologia",
    "posto de combustiv",
    "petrobras",
    "refinaria",
]

TIPOS_OPORTUNIDADE = {
    "ESPECIALIDADE": "Especialidade nao reconhecida",
    "PPP_FALTANTE": "PPP sem vinculo correspondente",
    "CARGO_SUGERE": "Cargo sugere especialidade",
    "RMI_ERRADA": "RMI possivelmente errada",
    "LACUNA_CONTRIB": "Periodo sem contribuicao",
    "MELHOR_BENEFICIO": "Beneficio ativo vs. melhor regra",
    "CONVERSAO_ESPECIAL": "Tempo especial conversivel",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> List[Dict]:
    """Garante que o valor seja uma lista de dicts, mesmo se None/vazio."""
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _safe_dict(value: Any) -> Dict:
    """Garante que o valor seja um dict, mesmo se None."""
    if isinstance(value, dict):
        return value
    return {}


def _parse_date(value: Any) -> Optional[date]:
    """Converte string ou datetime para date, retorna None se impossivel."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
    return None


def _normalizar_texto(texto: Optional[str]) -> str:
    """Normaliza texto para comparacao: lowercase, sem acentos simplificados."""
    if not texto:
        return ""
    t = texto.lower().strip()
    # Remocao simplificada de acentos comuns em portugues
    mapa = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñ",
        "aaaaaeeeeiiiiooooouuuucn",
    )
    return t.translate(mapa)


def _texto_contem_keyword(texto: str, keywords: Sequence[str]) -> Optional[str]:
    """Retorna a primeira keyword encontrada no texto normalizado, ou None."""
    texto_norm = _normalizar_texto(texto)
    for kw in keywords:
        if _normalizar_texto(kw) in texto_norm:
            return kw
    return None


def _periodos_se_sobrepoe(
    inicio1: Optional[date],
    fim1: Optional[date],
    inicio2: Optional[date],
    fim2: Optional[date],
) -> bool:
    """Verifica se dois periodos possuem sobreposicao."""
    if not all([inicio1, fim1, inicio2, fim2]):
        return False
    assert inicio1 and fim1 and inicio2 and fim2  # para o type-checker
    return inicio1 <= fim2 and inicio2 <= fim1


def _calcular_confianca_geral(oportunidades: List[Dict[str, Any]]) -> str:
    """Calcula confianca geral baseada nas oportunidades encontradas."""
    if not oportunidades:
        return "BAIXA"
    confiancas = [op.get("confianca", 0.0) for op in oportunidades]
    media = sum(confiancas) / len(confiancas)
    if media >= 0.7:
        return "ALTA"
    if media >= 0.4:
        return "MEDIA"
    return "BAIXA"


def _gerar_resumo(oportunidades: List[Dict[str, Any]]) -> str:
    """Gera resumo executivo das oportunidades encontradas."""
    total = len(oportunidades)
    if total == 0:
        return (
            "Nenhuma oportunidade identificada com os dados fornecidos. "
            "Recomenda-se verificar se todos os documentos foram enviados."
        )

    alta = sum(1 for op in oportunidades if op.get("confianca", 0) >= 0.7)
    media = sum(1 for op in oportunidades if 0.4 <= op.get("confianca", 0) < 0.7)
    baixa = sum(1 for op in oportunidades if op.get("confianca", 0) < 0.4)

    tipos_encontrados = set(op.get("tipo", "") for op in oportunidades)

    partes: List[str] = [
        f"Foram identificadas {total} oportunidade(s) previdenciaria(s).",
    ]

    if alta > 0:
        partes.append(f"{alta} com alta confianca.")
    if media > 0:
        partes.append(f"{media} com media confianca.")
    if baixa > 0:
        partes.append(f"{baixa} com baixa confianca.")

    if "ESPECIALIDADE" in tipos_encontrados or "CARGO_SUGERE" in tipos_encontrados:
        partes.append(
            "Ha indicios de atividade especial que podem aumentar o tempo de contribuicao."
        )
    if "RMI_ERRADA" in tipos_encontrados:
        partes.append("Possibilidade de revisao do valor do beneficio.")
    if "LACUNA_CONTRIB" in tipos_encontrados:
        partes.append("Existem lacunas contributivas que merecem investigacao.")
    if "CONVERSAO_ESPECIAL" in tipos_encontrados:
        partes.append(
            "Ha periodos especiais conversiveis anteriores a EC 103/2019."
        )

    return " ".join(partes)


# ---------------------------------------------------------------------------
# Detectores individuais
# ---------------------------------------------------------------------------


def _detectar_especialidade_nao_reconhecida(
    vinculos: List[Dict],
    ppps: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 1: CNIS mostra empresa com ramo tipicamente especial,
    mas nao ha PPP correspondente.
    """
    oportunidades: List[Dict[str, Any]] = []

    # Indexar PPPs por empresa/CNPJ para busca rapida
    ppps_empresas_norm: set[str] = set()
    ppps_cnpjs: set[str] = set()
    for ppp in ppps:
        empresa_ppp = ppp.get("empresa") or ppp.get("empregador") or ""
        if empresa_ppp:
            ppps_empresas_norm.add(_normalizar_texto(empresa_ppp))
        cnpj_ppp = ppp.get("cnpj") or ""
        if cnpj_ppp:
            ppps_cnpjs.add(re.sub(r"\D", "", cnpj_ppp))

    for vinculo in vinculos:
        empresa = vinculo.get("empresa") or vinculo.get("empregador") or ""
        cnpj = vinculo.get("cnpj") or ""
        cnpj_limpo = re.sub(r"\D", "", cnpj) if cnpj else ""

        # Verifica se ha PPP para esse vinculo
        empresa_norm = _normalizar_texto(empresa)
        tem_ppp = (
            empresa_norm in ppps_empresas_norm
            or (cnpj_limpo and cnpj_limpo in ppps_cnpjs)
        )

        if tem_ppp:
            continue

        # Verifica se o nome da empresa sugere atividade especial
        keyword = _texto_contem_keyword(empresa, EMPRESAS_ESPECIAIS_KEYWORDS)
        if not keyword:
            continue

        inicio = vinculo.get("inicio") or vinculo.get("data_inicio") or "N/I"
        fim = vinculo.get("fim") or vinculo.get("data_fim") or "atual"

        oportunidades.append({
            "tipo": "ESPECIALIDADE",
            "descricao": (
                f"A empresa '{empresa}' possui caracteristicas de atividade especial "
                f"(ramo: {keyword}), periodo {inicio} a {fim}, "
                f"mas nao ha PPP correspondente nos documentos enviados."
            ),
            "confianca": 0.7,
            "acao_recomendada": (
                f"Solicitar PPP ao empregador '{empresa}' "
                f"(CNPJ: {cnpj or 'nao informado'}) para o periodo {inicio} a {fim}."
            ),
            "documentos_necessarios": [
                "PPP - Perfil Profissiografico Previdenciario",
                "LTCAT do periodo (se disponivel)",
            ],
            "fundamentacao": (
                "Art. 57 e 58 da Lei 8.213/91; "
                "Art. 68 do Decreto 3.048/99; "
                "IN INSS/PRES 128/2022, art. 276 e ss."
            ),
            "impacto_estimado": (
                "Reconhecimento de tempo especial pode antecipar aposentadoria "
                "e/ou aumentar o valor do beneficio via conversao de tempo especial "
                "em comum (fator 1.4 homem / 1.2 mulher)."
            ),
        })

    return oportunidades


def _detectar_ppp_sem_vinculo(
    vinculos: List[Dict],
    ppps: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 2: PPP enviado mas sem vinculo correspondente no CNIS.
    """
    oportunidades: List[Dict[str, Any]] = []

    vinculos_empresas_norm: set[str] = set()
    vinculos_cnpjs: set[str] = set()
    for v in vinculos:
        emp = v.get("empresa") or v.get("empregador") or ""
        if emp:
            vinculos_empresas_norm.add(_normalizar_texto(emp))
        cnpj = v.get("cnpj") or ""
        if cnpj:
            vinculos_cnpjs.add(re.sub(r"\D", "", cnpj))

    for ppp in ppps:
        empresa = ppp.get("empresa") or ppp.get("empregador") or ""
        cnpj = ppp.get("cnpj") or ""
        cnpj_limpo = re.sub(r"\D", "", cnpj) if cnpj else ""

        empresa_norm = _normalizar_texto(empresa)

        tem_vinculo = (
            empresa_norm in vinculos_empresas_norm
            or (cnpj_limpo and cnpj_limpo in vinculos_cnpjs)
        )

        if tem_vinculo:
            continue

        inicio = ppp.get("inicio") or ppp.get("data_inicio") or "N/I"
        fim = ppp.get("fim") or ppp.get("data_fim") or "N/I"

        oportunidades.append({
            "tipo": "PPP_FALTANTE",
            "descricao": (
                f"PPP da empresa '{empresa}' (periodo {inicio} a {fim}) "
                f"nao possui vinculo correspondente no CNIS. "
                f"Pode haver vinculo nao registrado ou divergencia cadastral."
            ),
            "confianca": 0.8,
            "acao_recomendada": (
                "Verificar se este vinculo consta no CNIS. "
                "Se ausente, solicitar acerto de CNIS via requerimento administrativo "
                "ou acao judicial, apresentando o PPP como prova material."
            ),
            "documentos_necessarios": [
                "CNIS atualizado (extrato detalhado)",
                "CTPS com anotacao do vinculo",
                "PPP ja em maos",
                "Contracheques do periodo (se disponiveis)",
            ],
            "fundamentacao": (
                "Art. 29-A da Lei 8.213/91; "
                "Art. 19-B do Decreto 3.048/99; "
                "Tema 1124 do STJ (prova do tempo de servico)."
            ),
            "impacto_estimado": (
                "Inclusao de vinculo no CNIS pode acrescentar tempo de contribuicao "
                "e salarios-de-contribuicao ao calculo do beneficio."
            ),
        })

    return oportunidades


def _detectar_cargo_sugere_especialidade(
    vinculos: List[Dict],
    analise_especial: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 3: cargo registrado na CTPS/CNIS sugere atividade especial.
    """
    oportunidades: List[Dict[str, Any]] = []

    # Periodos ja reconhecidos como especiais
    periodos_especiais: List[Tuple[Optional[date], Optional[date]]] = []
    for ae in analise_especial:
        di = _parse_date(ae.get("inicio") or ae.get("data_inicio"))
        df = _parse_date(ae.get("fim") or ae.get("data_fim"))
        if di and df:
            periodos_especiais.append((di, df))

    for vinculo in vinculos:
        cargo = vinculo.get("cargo") or vinculo.get("funcao") or ""
        cargo_norm = _normalizar_texto(cargo)

        if not cargo_norm:
            continue

        # Busca no dicionario de cargos especiais
        agente_encontrado: Optional[str] = None
        for cargo_chave, agente in CARGOS_ESPECIAIS.items():
            if cargo_chave in cargo_norm:
                agente_encontrado = agente
                break

        if not agente_encontrado:
            continue

        # Verifica se o periodo ja esta reconhecido como especial
        di_vinc = _parse_date(vinculo.get("inicio") or vinculo.get("data_inicio"))
        df_vinc = _parse_date(vinculo.get("fim") or vinculo.get("data_fim"))

        ja_reconhecido = any(
            _periodos_se_sobrepoe(di_vinc, df_vinc, di_esp, df_esp)
            for di_esp, df_esp in periodos_especiais
        )

        if ja_reconhecido:
            continue

        empresa = vinculo.get("empresa") or vinculo.get("empregador") or "N/I"
        inicio = vinculo.get("inicio") or vinculo.get("data_inicio") or "N/I"
        fim = vinculo.get("fim") or vinculo.get("data_fim") or "atual"

        oportunidades.append({
            "tipo": "CARGO_SUGERE",
            "descricao": (
                f"O cargo '{cargo}' na empresa '{empresa}' "
                f"(periodo {inicio} a {fim}) e tipicamente enquadrado como "
                f"atividade especial. {agente_encontrado}."
            ),
            "confianca": 0.6,
            "acao_recomendada": (
                f"Solicitar PPP e LTCAT ao empregador '{empresa}'. "
                f"Caso a empresa esteja inativa, buscar LTCAT no acervo da SRTE "
                f"ou prova emprestada de ex-colegas."
            ),
            "documentos_necessarios": [
                "PPP - Perfil Profissiografico Previdenciario",
                "LTCAT - Laudo Tecnico das Condicoes Ambientais do Trabalho",
                "Prova testemunhal (subsidiariamente)",
            ],
            "fundamentacao": (
                "Art. 57 da Lei 8.213/91; "
                "Decreto 53.831/64 e Decreto 83.080/79 (enquadramento por categoria); "
                "Sumula 198 do extinto TFR; "
                "Tema 534 do STJ (ruido)."
            ),
            "impacto_estimado": (
                f"Reconhecimento de atividade especial no periodo pode resultar "
                f"em conversao de tempo com fator multiplicador e/ou "
                f"antecipacao da data de aposentadoria."
            ),
        })

    return oportunidades


def _detectar_rmi_errada(
    beneficios: List[Dict],
    carta_concessao: Optional[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 4: RMI da carta de concessao diverge do recalculo.
    """
    oportunidades: List[Dict[str, Any]] = []
    carta = _safe_dict(carta_concessao)

    if not carta:
        return oportunidades

    rmi_carta = carta.get("rmi") or carta.get("valor_rmi")
    rmi_recalculado = carta.get("rmi_recalculado") or carta.get("valor_recalculado")

    if rmi_carta is None or rmi_recalculado is None:
        # Sem dados para comparacao, verificar se ha beneficio ativo com RMI
        for ben in beneficios:
            if ben.get("situacao", "").lower() in ("ativo", "ativa"):
                rmi_ben = ben.get("rmi") or ben.get("valor")
                if rmi_ben is not None and rmi_carta is not None:
                    rmi_recalculado = rmi_ben
                    break

    if rmi_carta is None or rmi_recalculado is None:
        return oportunidades

    try:
        rmi_carta_float = float(rmi_carta)
        rmi_recalculado_float = float(rmi_recalculado)
    except (ValueError, TypeError):
        return oportunidades

    if rmi_recalculado_float <= 0 or rmi_carta_float <= 0:
        return oportunidades

    diferenca = rmi_recalculado_float - rmi_carta_float
    percentual = (diferenca / rmi_carta_float) * 100

    # So reportar se o recalculo for significativamente maior (> 2%)
    if percentual <= 2.0:
        return oportunidades

    confianca = min(0.9, 0.5 + (percentual / 100))

    nb = carta.get("nb") or carta.get("numero_beneficio") or "N/I"
    dib = carta.get("dib") or carta.get("data_inicio_beneficio") or "N/I"
    especie = carta.get("especie") or carta.get("tipo_beneficio") or "N/I"

    oportunidades.append({
        "tipo": "RMI_ERRADA",
        "descricao": (
            f"A RMI da carta de concessao (R$ {rmi_carta_float:,.2f}) "
            f"diverge do valor recalculado (R$ {rmi_recalculado_float:,.2f}). "
            f"Diferenca de {percentual:.1f}% "
            f"(R$ {abs(diferenca):,.2f}). "
            f"Beneficio NB {nb}, especie {especie}, DIB {dib}."
        ),
        "confianca": round(confianca, 2),
        "acao_recomendada": (
            "Ingressar com pedido de revisao administrativa ou judicial. "
            "Verificar se houve erro no calculo do salario-de-beneficio, "
            "na aplicacao do fator previdenciario ou no coeficiente de calculo."
        ),
        "documentos_necessarios": [
            "Carta de concessao completa",
            "Memorias de calculo do INSS",
            "CNIS detalhado com salarios-de-contribuicao",
            "Planilha de recalculo atualizada",
        ],
        "fundamentacao": (
            "Art. 103-A da Lei 8.213/91 (decadencia); "
            "Tema 966 do STF (revisao da vida toda); "
            "Art. 29, II, da Lei 8.213/91 (calculo do SB)."
        ),
        "impacto_estimado": (
            f"Revisao da RMI pode gerar diferenca mensal de "
            f"R$ {abs(diferenca):,.2f} ({percentual:.1f}%), "
            f"alem de atrasados desde a DIB (respeitada a prescricao quinquenal)."
        ),
    })

    return oportunidades


def _detectar_lacunas_contribuicao(
    vinculos: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 5: lacunas significativas entre vinculos de contribuicao.
    """
    oportunidades: List[Dict[str, Any]] = []

    # Coletar e ordenar periodos
    periodos: List[Tuple[date, date, str]] = []
    for v in vinculos:
        di = _parse_date(v.get("inicio") or v.get("data_inicio"))
        df = _parse_date(v.get("fim") or v.get("data_fim"))
        empresa = v.get("empresa") or v.get("empregador") or "N/I"
        if di and df and df >= di:
            periodos.append((di, df, empresa))

    if len(periodos) < 2:
        return oportunidades

    periodos.sort(key=lambda p: p[0])

    for i in range(len(periodos) - 1):
        _, fim_atual, emp_atual = periodos[i]
        inicio_prox, _, emp_prox = periodos[i + 1]

        gap_dias = (inicio_prox - fim_atual).days

        # So considerar gaps maiores que 60 dias (evitar falsos positivos)
        if gap_dias <= 60:
            continue

        gap_meses = gap_dias / 30.44  # media de dias por mes

        # Confianca proporcional ao tamanho da lacuna
        if gap_meses >= 24:
            confianca = 0.8
        elif gap_meses >= 12:
            confianca = 0.6
        else:
            confianca = 0.4

        oportunidades.append({
            "tipo": "LACUNA_CONTRIB",
            "descricao": (
                f"Lacuna de aproximadamente {int(gap_meses)} mese(s) "
                f"({gap_dias} dias) entre o fim do vinculo com '{emp_atual}' "
                f"({fim_atual.strftime('%d/%m/%Y')}) e o inicio do vinculo "
                f"com '{emp_prox}' ({inicio_prox.strftime('%d/%m/%Y')})."
            ),
            "confianca": confianca,
            "acao_recomendada": (
                "Investigar se ha contribuicoes como contribuinte individual, "
                "facultativo ou em regime proprio (servidor) nesse periodo. "
                "Verificar tambem se houve recebimento de beneficio por incapacidade "
                "ou seguro-desemprego."
            ),
            "documentos_necessarios": [
                "CNIS completo e atualizado",
                "Guias de recolhimento (GPS) do periodo",
                "CTPS (verificar anotacoes nao registradas no CNIS)",
                "Extratos bancarios do periodo (se aplicavel)",
            ],
            "fundamentacao": (
                "Art. 96 da Lei 8.213/91 (contagem reciproca); "
                "Art. 60 do Decreto 3.048/99 (periodo de graca); "
                "Art. 11 da Lei 8.213/91 (segurados obrigatorios)."
            ),
            "impacto_estimado": (
                f"Recuperacao de {int(gap_meses)} mese(s) de contribuicao "
                f"pode adiantar a aposentadoria e/ou elevar o salario-de-beneficio."
            ),
        })

    return oportunidades


def _detectar_melhor_beneficio(
    beneficios: List[Dict],
    vinculos: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 6: beneficio ativo mas tempo de contribuicao sugere
    que regra mais vantajosa estava disponivel.
    """
    oportunidades: List[Dict[str, Any]] = []

    beneficios_ativos = [
        b for b in beneficios
        if (b.get("situacao") or "").lower() in ("ativo", "ativa")
    ]

    if not beneficios_ativos:
        return oportunidades

    # Calcular tempo total de contribuicao aproximado
    total_dias = 0
    for v in vinculos:
        di = _parse_date(v.get("inicio") or v.get("data_inicio"))
        df = _parse_date(v.get("fim") or v.get("data_fim"))
        if di and df and df >= di:
            total_dias += (df - di).days

    total_anos = total_dias / 365.25

    for ben in beneficios_ativos:
        especie = (ben.get("especie") or ben.get("tipo") or "").lower()
        dib = _parse_date(ben.get("dib") or ben.get("data_inicio"))

        # Regra geral: se tem mais de 35 anos (H) ou 30 anos (M)
        # e o beneficio foi concedido apos a Reforma, verificar regras de transicao
        if dib and dib >= date(2019, 11, 13) and total_anos >= 30:
            nb = ben.get("nb") or ben.get("numero_beneficio") or "N/I"
            regra_aplicada = ben.get("regra") or ben.get("regra_transicao") or "nao informada"

            oportunidades.append({
                "tipo": "MELHOR_BENEFICIO",
                "descricao": (
                    f"Beneficio NB {nb} (especie: {especie or 'N/I'}) "
                    f"concedido com {total_anos:.1f} anos de contribuicao. "
                    f"Regra aplicada: {regra_aplicada}. "
                    f"Com esse tempo, pode haver regra de transicao mais vantajosa."
                ),
                "confianca": 0.5,
                "acao_recomendada": (
                    "Realizar simulacao de todas as regras de transicao "
                    "(pedagio 50%, pedagio 100%, idade progressiva, pontos) "
                    "para verificar qual produz melhor RMI. "
                    "Comparar com o beneficio atual."
                ),
                "documentos_necessarios": [
                    "CNIS detalhado com salarios",
                    "Carta de concessao",
                    "Memorias de calculo do INSS",
                    "Planilha de simulacao com todas as regras",
                ],
                "fundamentacao": (
                    "Art. 15 a 21 da EC 103/2019 (regras de transicao); "
                    "Principio do melhor beneficio (art. 687, IN 128/2022)."
                ),
                "impacto_estimado": (
                    "A aplicacao da regra de transicao mais vantajosa pode "
                    "resultar em coeficiente de calculo superior e/ou "
                    "afastamento do divisor minimo."
                ),
            })

    return oportunidades


def _detectar_conversao_especial(
    analise_especial: List[Dict],
    ppps: List[Dict],
    documentos: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Oportunidade 7: periodos com evidencia de especialidade anteriores
    a 13/11/2019 que podem ser convertidos.
    """
    oportunidades: List[Dict[str, Any]] = []

    # Consolidar todos os periodos com evidencia de atividade especial
    periodos_especiais: List[Dict] = []

    for ae in analise_especial:
        di = _parse_date(ae.get("inicio") or ae.get("data_inicio"))
        df = _parse_date(ae.get("fim") or ae.get("data_fim"))
        if di and df:
            periodos_especiais.append({
                "inicio": di,
                "fim": df,
                "empresa": ae.get("empresa") or ae.get("empregador") or "N/I",
                "agente": ae.get("agente_nocivo") or ae.get("agente") or "N/I",
                "fonte": "analise_especial",
                "convertido": ae.get("convertido", False),
            })

    for ppp in ppps:
        di = _parse_date(ppp.get("inicio") or ppp.get("data_inicio"))
        df = _parse_date(ppp.get("fim") or ppp.get("data_fim"))
        if di and df:
            periodos_especiais.append({
                "inicio": di,
                "fim": df,
                "empresa": ppp.get("empresa") or ppp.get("empregador") or "N/I",
                "agente": ppp.get("agente_nocivo") or ppp.get("agente") or "N/I",
                "fonte": "ppp",
                "convertido": ppp.get("convertido", False),
            })

    for doc in documentos:
        tipo_doc = _normalizar_texto(doc.get("tipo") or "")
        if "ltcat" not in tipo_doc and "laudo" not in tipo_doc:
            continue
        di = _parse_date(doc.get("inicio") or doc.get("data_inicio"))
        df = _parse_date(doc.get("fim") or doc.get("data_fim"))
        if di and df:
            periodos_especiais.append({
                "inicio": di,
                "fim": df,
                "empresa": doc.get("empresa") or doc.get("empregador") or "N/I",
                "agente": doc.get("agente_nocivo") or doc.get("agente") or "N/I",
                "fonte": "ltcat",
                "convertido": doc.get("convertido", False),
            })

    for periodo in periodos_especiais:
        inicio: date = periodo["inicio"]
        fim: date = periodo["fim"]

        # So interessa se o periodo e anterior a EC 103/2019
        if inicio >= DATA_LIMITE_CONVERSAO:
            continue

        # Ja foi convertido? Pular
        if periodo.get("convertido"):
            continue

        # Ajustar fim se posterior a data limite
        fim_conversao = min(fim, DATA_LIMITE_CONVERSAO - timedelta(days=1))
        dias_conversiveis = (fim_conversao - inicio).days

        if dias_conversiveis <= 30:  # menos de 1 mes nao vale reportar
            continue

        anos_conv = dias_conversiveis / 365.25
        # Ganho estimado com fator 1.4 (homem) - sera o caso mais comum
        ganho_dias_estimado = int(dias_conversiveis * 0.4)
        ganho_meses_estimado = ganho_dias_estimado / 30.44

        oportunidades.append({
            "tipo": "CONVERSAO_ESPECIAL",
            "descricao": (
                f"Periodo de {inicio.strftime('%d/%m/%Y')} a "
                f"{fim_conversao.strftime('%d/%m/%Y')} "
                f"({anos_conv:.1f} anos) na empresa '{periodo['empresa']}' "
                f"com agente nocivo '{periodo['agente']}' "
                f"e anterior a EC 103/2019, sendo conversivel em tempo comum."
            ),
            "confianca": 0.75,
            "acao_recomendada": (
                "Requerer a conversao de tempo especial em comum "
                "com aplicacao do fator multiplicador (1.4 homem / 1.2 mulher). "
                "Se o INSS ja indeferiu, avaliar acao judicial."
            ),
            "documentos_necessarios": [
                "PPP do periodo",
                "LTCAT (se existente)",
                "CNIS atualizado",
                "Formularios antigos (SB-40, DISES-BE 5235, DSS-8030) se aplicavel",
            ],
            "fundamentacao": (
                "Art. 57, par. 5, da Lei 8.213/91; "
                "Art. 70 do Decreto 3.048/99; "
                "Tema 422 do STF (conversao ate a EC 103/2019); "
                "Art. 25, par. 2, da EC 103/2019."
            ),
            "impacto_estimado": (
                f"Conversao de {anos_conv:.1f} anos de tempo especial resulta "
                f"em ganho estimado de {ganho_meses_estimado:.0f} mese(s) "
                f"de tempo de contribuicao (fator 1.4 homem / 1.2 mulher)."
            ),
        })

    return oportunidades


# ---------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------


def analisar_cruzamento(
    vinculos: List[Dict],
    beneficios: List[Dict],
    analise_especial: List[Dict],
    ppps: List[Dict],
    documentos: List[Dict],
    carta_concessao: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Motor principal do Detetive Previdenciario.

    Cruza dados de multiplos documentos para encontrar oportunidades
    previdenciarias automaticamente.

    Args:
        vinculos: Lista de vinculos empregatitios (CNIS/CTPS). Cada dict
            pode conter: empresa, cnpj, cargo, inicio/data_inicio,
            fim/data_fim.
        beneficios: Lista de beneficios do CNIS. Cada dict pode conter:
            nb, especie, situacao, dib, rmi.
        analise_especial: Lista de periodos ja analisados como especiais.
            Cada dict pode conter: empresa, agente_nocivo, inicio, fim,
            convertido.
        ppps: Lista de PPPs enviados. Cada dict pode conter: empresa,
            cnpj, inicio, fim, agente_nocivo.
        documentos: Lista de documentos adicionais (LTCAT, laudos).
            Cada dict pode conter: tipo, empresa, inicio, fim,
            agente_nocivo.
        carta_concessao: Dados da carta de concessao (opcional). Dict pode
            conter: rmi, rmi_recalculado, nb, dib, especie.

    Returns:
        Dict com: oportunidades (lista ordenada por confianca),
        resumo (texto executivo), total_oportunidades, confianca_geral.
    """
    # Sanitizar entradas
    vinculos_safe = _safe_list(vinculos)
    beneficios_safe = _safe_list(beneficios)
    analise_safe = _safe_list(analise_especial)
    ppps_safe = _safe_list(ppps)
    docs_safe = _safe_list(documentos)
    carta_safe = _safe_dict(carta_concessao)

    # Coletar todas as oportunidades
    todas_oportunidades: List[Dict[str, Any]] = []

    # 1. Especialidade nao reconhecida
    todas_oportunidades.extend(
        _detectar_especialidade_nao_reconhecida(vinculos_safe, ppps_safe)
    )

    # 2. PPP sem vinculo correspondente
    todas_oportunidades.extend(
        _detectar_ppp_sem_vinculo(vinculos_safe, ppps_safe)
    )

    # 3. Cargo sugere especialidade
    todas_oportunidades.extend(
        _detectar_cargo_sugere_especialidade(vinculos_safe, analise_safe)
    )

    # 4. RMI possivelmente errada
    todas_oportunidades.extend(
        _detectar_rmi_errada(beneficios_safe, carta_safe or None)
    )

    # 5. Lacunas de contribuicao
    todas_oportunidades.extend(
        _detectar_lacunas_contribuicao(vinculos_safe)
    )

    # 6. Beneficio ativo vs. melhor regra
    todas_oportunidades.extend(
        _detectar_melhor_beneficio(beneficios_safe, vinculos_safe)
    )

    # 7. Tempo especial conversivel
    todas_oportunidades.extend(
        _detectar_conversao_especial(analise_safe, ppps_safe, docs_safe)
    )

    # Ordenar por confianca (maior primeiro)
    todas_oportunidades.sort(key=lambda x: x.get("confianca", 0), reverse=True)

    return {
        "oportunidades": todas_oportunidades,
        "resumo": _gerar_resumo(todas_oportunidades),
        "total_oportunidades": len(todas_oportunidades),
        "confianca_geral": _calcular_confianca_geral(todas_oportunidades),
    }
