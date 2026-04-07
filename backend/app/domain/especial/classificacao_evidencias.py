"""
Classificacao de evidencias para atividade especial em camadas (tiers).

Sistema de classificacao baseado em lastro probatorio, nao apenas
correspondencia de nome. Cada vinculo recebe uma classificacao de 1 a 5
conforme a qualidade e quantidade de provas disponíveis.

TIER 1 - PROVA_FORTE: PPP + LTCAT confirmam agente + empresa + periodo
TIER 2 - PROVA_MEDIA: CBO + CNAE + jurisprudencia convergem (sem PPP/LTCAT)
TIER 3 - INDICIO_RELEVANTE: Nome ou funcao sugerem, mas falta lastro documental
TIER 4 - INDICIO_FRACO: Apenas correspondencia de nome do empregador
TIER 5 - SEM_LASTRO: Nenhuma evidencia encontrada

Fundamentacao: Lei 8.213/91 art. 57-58; Decreto 3.048/99 Anexo IV;
IN INSS/PRES 77/2015; IN INSS/PRES 128/2022.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de Tier
# ─────────────────────────────────────────────────────────────────────────────

TIER_PROVA_FORTE = 1
TIER_PROVA_MEDIA = 2
TIER_INDICIO_RELEVANTE = 3
TIER_INDICIO_FRACO = 4
TIER_SEM_LASTRO = 5

TIER_LABELS = {
    1: "PROVA_FORTE",
    2: "PROVA_MEDIA",
    3: "INDICIO_RELEVANTE",
    4: "INDICIO_FRACO",
    5: "SEM_LASTRO",
}

TIER_TO_PROBABILIDADE = {
    1: "ALTA",
    2: "MEDIA",
    3: "BAIXA",
    4: "BAIXA",
    5: "NENHUMA",
}

ALERTA_SEM_LASTRO = (
    "HA INDICIOS DE ATIVIDADE ESPECIAL, MAS NAO HA LASTRO "
    "SUFICIENTE PARA RECONHECIMENTO AUTOMATICO"
)


# ─────────────────────────────────────────────────────────────────────────────
# Estruturas de dados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Evidencia:
    """Uma evidencia individual encontrada na analise."""
    fonte: str          # "CBO", "CNAE", "EMPREGADOR_NOME", "PPP", "LTCAT", "CARGO", "JURISPRUDENCIA"
    descricao: str      # Descricao legivel da evidencia
    peso: str           # "FORTE", "MEDIO", "FRACO"
    detalhes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificacaoEspecial:
    """Resultado da classificacao de evidencias para um vinculo."""
    tier: int
    tier_label: str
    evidencias: List[Evidencia]
    documentos_faltantes: List[str]
    pode_reconhecer_automatico: bool
    mensagem_advogado: str
    fundamentacao_legal: List[str]
    alerta_sem_lastro: Optional[str] = None

    # Campos de compatibilidade com o frontend existente
    possivel: bool = False
    probabilidade: str = "NENHUMA"
    agentes: List[str] = field(default_factory=list)
    fundamentacao: str = ""
    via: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializa para dict compativel com a resposta da API."""
        result = {
            # Novos campos do sistema de tiers
            "tier": self.tier,
            "tier_label": self.tier_label,
            "evidencias": [
                {
                    "fonte": e.fonte,
                    "descricao": e.descricao,
                    "peso": e.peso,
                    "detalhes": e.detalhes,
                }
                for e in self.evidencias
            ],
            "documentos_faltantes": self.documentos_faltantes,
            "pode_reconhecer_automatico": self.pode_reconhecer_automatico,
            "mensagem_advogado": self.mensagem_advogado,
            "fundamentacao_legal": self.fundamentacao_legal,
            # Campos de compatibilidade com frontend existente
            "possivel": self.possivel,
            "probabilidade": self.probabilidade,
            "agentes": self.agentes,
            "fundamentacao": self.fundamentacao,
            "via": self.via,
        }
        if self.alerta_sem_lastro:
            result["alerta_sem_lastro"] = self.alerta_sem_lastro
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Funcao principal de classificacao
# ─────────────────────────────────────────────────────────────────────────────

def classificar_evidencias(
    analise_empregador: Dict[str, Any],
    analise_cargo: Dict[str, Any],
    analise_cbo: Optional[Dict[str, Any]],
    jurisprudencias: list,
    tem_ppp: bool = False,
    ppp_confirma_agente: bool = False,
    ppp_empresa_match: bool = False,
    ppp_periodo_match: bool = False,
    tem_ltcat: bool = False,
    ltcat_confirma_exposicao: bool = False,
    empregador_nome: str = "",
    cargo: str = "",
    cbo: str = "",
) -> ClassificacaoEspecial:
    """
    Classifica o nivel de evidencia para atividade especial de um vinculo.

    Analisa multiplas fontes de evidencia e atribui um tier de 1 a 5.
    Mantem compatibilidade com os campos que o frontend espera.

    Args:
        analise_empregador: Resultado de verificar_possivel_especial() para o empregador
        analise_cargo: Resultado de verificar_possivel_especial() para o cargo
        analise_cbo: Resultado de analisar_cbo() ou None
        jurisprudencias: Lista de jurisprudencias encontradas
        tem_ppp: Se um PPP foi uploaded para este vinculo
        ppp_confirma_agente: Se o PPP confirma exposicao a agente nocivo
        ppp_empresa_match: Se o PPP corresponde ao empregador do vinculo
        ppp_periodo_match: Se o PPP cobre o periodo do vinculo
        tem_ltcat: Se um LTCAT foi uploaded para este vinculo
        ltcat_confirma_exposicao: Se o LTCAT confirma exposicao acima da tolerancia
        empregador_nome: Nome do empregador (para mensagens)
        cargo: Cargo exercido (para mensagens)
        cbo: Codigo CBO (para mensagens)

    Returns:
        ClassificacaoEspecial com tier, evidencias, e campos de compatibilidade
    """
    evidencias: List[Evidencia] = []
    fundamentacao_legal: List[str] = []
    agentes_encontrados: List[str] = []
    docs_faltantes: List[str] = []

    # ── Coletar evidencias de cada fonte ──────────────────────────────────

    # Flags para determinar tier
    flag_ppp_completo = False
    flag_ltcat_confirma = False
    flag_cbo_especial = False
    flag_cnae_ou_empregador_especial = False
    flag_cargo_sugere = False
    flag_nome_match = False
    flag_juris_apoia = False

    # 1. PPP
    if tem_ppp and ppp_confirma_agente and ppp_empresa_match and ppp_periodo_match:
        flag_ppp_completo = True
        evidencias.append(Evidencia(
            fonte="PPP",
            descricao="PPP confirma exposicao a agente nocivo, com empresa e periodo correspondentes",
            peso="FORTE",
        ))
    elif tem_ppp:
        evidencias.append(Evidencia(
            fonte="PPP",
            descricao="PPP presente, mas dados parciais (verificar agente, empresa ou periodo)",
            peso="MEDIO",
        ))
    else:
        docs_faltantes.append(
            "PPP (Perfil Profissiografico Previdenciario) — solicitar ao empregador"
        )

    # 2. LTCAT
    if tem_ltcat and ltcat_confirma_exposicao:
        flag_ltcat_confirma = True
        evidencias.append(Evidencia(
            fonte="LTCAT",
            descricao="LTCAT confirma exposicao acima dos limites de tolerancia",
            peso="FORTE",
        ))
    elif tem_ltcat:
        evidencias.append(Evidencia(
            fonte="LTCAT",
            descricao="LTCAT presente, mas nao confirma exposicao acima dos limites",
            peso="MEDIO",
        ))
    else:
        docs_faltantes.append(
            "LTCAT (Laudo Tecnico das Condicoes Ambientais de Trabalho)"
        )

    # 3. CBO
    if analise_cbo and analise_cbo.get("possivel_especial"):
        flag_cbo_especial = True
        prob_cbo = analise_cbo.get("probabilidade", "BAIXA")
        desc_cbo = analise_cbo.get("descricao_cbo", f"CBO {cbo}")
        peso = "FORTE" if prob_cbo == "ALTA" else "MEDIO"
        evidencias.append(Evidencia(
            fonte="CBO",
            descricao=f"{desc_cbo} — probabilidade {prob_cbo} de atividade especial",
            peso=peso,
            detalhes={
                "cbo": cbo,
                "probabilidade": prob_cbo,
                "nrs": analise_cbo.get("nrs_aplicaveis", []),
            },
        ))
        for a in analise_cbo.get("agentes_provaveis", []):
            codigo = a.get("codigo", str(a)) if isinstance(a, dict) else str(a)
            if codigo not in agentes_encontrados:
                agentes_encontrados.append(codigo)
        if analise_cbo.get("fundamentacao"):
            fundamentacao_legal.append(analise_cbo["fundamentacao"])

    # 4. Empregador (match por nome/CNAE)
    if analise_empregador.get("possivel_especial"):
        flag_nome_match = True
        prob_emp = analise_empregador.get("probabilidade", "BAIXA")
        padroes = analise_empregador.get("padroes_encontrados", [])
        categorias = [p.get("categoria", "") for p in padroes] if padroes else []
        peso = "MEDIO" if prob_emp in ("ALTA", "MEDIA") else "FRACO"

        # Distinguish: if empregador analysis comes from CNAE data, it's stronger
        # than pure name matching. For now, treat all empregador matches as name-based.
        flag_cnae_ou_empregador_especial = prob_emp in ("ALTA", "MEDIA")

        evidencias.append(Evidencia(
            fonte="EMPREGADOR_NOME",
            descricao=(
                f"Nome do empregador '{empregador_nome}' corresponde a "
                f"padroes de atividade com risco: {', '.join(categorias) if categorias else prob_emp}"
            ),
            peso=peso,
            detalhes={
                "padroes": padroes,
                "probabilidade": prob_emp,
            },
        ))
        for a in analise_empregador.get("agentes_provaveis", []):
            codigo = a.get("codigo", str(a)) if isinstance(a, dict) else str(a)
            if codigo not in agentes_encontrados:
                agentes_encontrados.append(codigo)
        if analise_empregador.get("fundamentacao"):
            fundamentacao_legal.append(analise_empregador["fundamentacao"])

    # 5. Cargo (match por nome do cargo)
    if analise_cargo.get("possivel_especial"):
        flag_cargo_sugere = True
        prob_cargo = analise_cargo.get("probabilidade", "BAIXA")
        evidencias.append(Evidencia(
            fonte="CARGO",
            descricao=f"Cargo '{cargo}' sugere possivel exposicao a agentes nocivos ({prob_cargo})",
            peso="MEDIO" if prob_cargo in ("ALTA", "MEDIA") else "FRACO",
            detalhes={"probabilidade": prob_cargo},
        ))
        for a in analise_cargo.get("agentes_provaveis", []):
            codigo = a.get("codigo", str(a)) if isinstance(a, dict) else str(a)
            if codigo not in agentes_encontrados:
                agentes_encontrados.append(codigo)
        if analise_cargo.get("fundamentacao"):
            fundamentacao_legal.append(analise_cargo["fundamentacao"])

    # 6. Jurisprudencia
    if jurisprudencias:
        flag_juris_apoia = True
        resumo_juris = []
        for j in jurisprudencias[:3]:  # Listar ate 3 principais
            if isinstance(j, dict):
                resumo_juris.append(f"{j.get('tipo', '')} {j.get('numero', '')} ({j.get('tribunal', '')})")
            else:
                resumo_juris.append(f"{j.tipo} {j.numero} ({j.tribunal})")
        evidencias.append(Evidencia(
            fonte="JURISPRUDENCIA",
            descricao=f"Jurisprudencia favoravel encontrada: {'; '.join(resumo_juris)}",
            peso="MEDIO",
            detalhes={"quantidade": len(jurisprudencias)},
        ))

    # ── Determinar o Tier ─────────────────────────────────────────────────

    tier = TIER_SEM_LASTRO  # Default

    # TIER 1: PPP completo + (LTCAT confirma OU PPP por si so e suficiente - Tema 208 STJ)
    if flag_ppp_completo and (flag_ltcat_confirma or True):
        # PPP que confirma agente + empresa + periodo ja e prova forte (Tema 208 STJ)
        tier = TIER_PROVA_FORTE

    # TIER 2: CBO especial + (empregador OU cargo converge) + jurisprudencia apoia
    elif flag_cbo_especial and (flag_cnae_ou_empregador_especial or flag_cargo_sugere) and flag_juris_apoia:
        tier = TIER_PROVA_MEDIA

    # Tambem TIER 2 se CBO e forte e jurisprudencia apoia (mesmo sem nome)
    elif flag_cbo_especial and analise_cbo and analise_cbo.get("probabilidade") == "ALTA" and flag_juris_apoia:
        tier = TIER_PROVA_MEDIA

    # TIER 3: Nome OU funcao sugere + pelo menos mais uma evidencia
    elif (flag_nome_match or flag_cargo_sugere) and (flag_cbo_especial or flag_juris_apoia):
        tier = TIER_INDICIO_RELEVANTE

    # Tambem TIER 3: CBO especial mas sem jurisprudencia ou convergencia
    elif flag_cbo_especial:
        tier = TIER_INDICIO_RELEVANTE

    # TIER 4: Apenas nome do empregador ou apenas cargo
    elif flag_nome_match or flag_cargo_sugere:
        tier = TIER_INDICIO_FRACO

    # TIER 5: Nada encontrado
    else:
        tier = TIER_SEM_LASTRO

    # ── Montar documentos faltantes por tier ──────────────────────────────

    if tier >= TIER_PROVA_MEDIA and not tem_ppp:
        # PPP sempre necessario para upgrade
        pass  # ja adicionado acima
    if tier >= TIER_PROVA_MEDIA and not tem_ltcat:
        pass  # ja adicionado acima

    if tier == TIER_PROVA_MEDIA:
        docs_faltantes_upgrade = [
            d for d in docs_faltantes
            if "PPP" in d  # PPP e o principal para upgrade de tier 2 para 1
        ]
        if not docs_faltantes_upgrade and not tem_ppp:
            docs_faltantes.append(
                "PPP (Perfil Profissiografico Previdenciario) para confirmar exposicao"
            )

    if tier == TIER_INDICIO_RELEVANTE:
        if not flag_cbo_especial:
            docs_faltantes.append(
                "Verificar codigo CBO correto do vinculo para cruzamento"
            )
        if not flag_juris_apoia:
            docs_faltantes.append(
                "Pesquisar jurisprudencia especifica para esta atividade/agente"
            )

    if tier == TIER_INDICIO_FRACO:
        docs_faltantes.append(
            "Verificar CBO e funcao real exercida junto ao segurado"
        )
        docs_faltantes.append(
            "Solicitar PPP ao empregador — indispensavel para comprovar exposicao"
        )

    # ── Mensagem para o advogado ──────────────────────────────────────────

    mensagem = _gerar_mensagem_advogado(
        tier=tier,
        empregador_nome=empregador_nome,
        cargo=cargo,
        cbo=cbo,
        agentes=agentes_encontrados,
        docs_faltantes=docs_faltantes,
        flag_cbo_especial=flag_cbo_especial,
        flag_nome_match=flag_nome_match,
    )

    # ── Campos de compatibilidade com frontend ────────────────────────────

    tier_label = TIER_LABELS[tier]
    probabilidade = TIER_TO_PROBABILIDADE[tier]
    possivel = tier <= TIER_INDICIO_FRACO  # Tiers 1-4 indicam possibilidade

    # Melhor fundamentacao consolidada
    fundamentacao_str = "; ".join(list(dict.fromkeys(fundamentacao_legal))) if fundamentacao_legal else ""

    # Determinar "via" principal
    if flag_ppp_completo:
        via = "ppp"
    elif flag_cbo_especial:
        via = "cbo"
    elif flag_cargo_sugere:
        via = "cargo"
    elif flag_nome_match:
        via = "empregador"
    else:
        via = ""

    # Alerta para tiers >= 3
    alerta = ALERTA_SEM_LASTRO if tier >= TIER_INDICIO_RELEVANTE and tier <= TIER_INDICIO_FRACO else None

    return ClassificacaoEspecial(
        tier=tier,
        tier_label=tier_label,
        evidencias=evidencias,
        documentos_faltantes=docs_faltantes,
        pode_reconhecer_automatico=(tier == TIER_PROVA_FORTE),
        mensagem_advogado=mensagem,
        fundamentacao_legal=fundamentacao_legal,
        alerta_sem_lastro=alerta,
        # Compatibilidade
        possivel=possivel,
        probabilidade=probabilidade,
        agentes=agentes_encontrados,
        fundamentacao=fundamentacao_str,
        via=via,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Geracao de mensagem para o advogado
# ─────────────────────────────────────────────────────────────────────────────

def _gerar_mensagem_advogado(
    tier: int,
    empregador_nome: str,
    cargo: str,
    cbo: str,
    agentes: List[str],
    docs_faltantes: List[str],
    flag_cbo_especial: bool,
    flag_nome_match: bool,
) -> str:
    """Gera mensagem orientativa para o advogado conforme o tier."""

    nome_display = empregador_nome or "empregador nao identificado"
    cargo_display = cargo or "cargo nao informado"

    if tier == TIER_PROVA_FORTE:
        return (
            f"PROVA FORTE para '{nome_display}'. "
            f"PPP e/ou LTCAT confirmam exposicao a agente(s) nocivo(s): "
            f"{', '.join(agentes) if agentes else 'ver documentos'}. "
            f"Periodo especial pode ser reconhecido com base documental solida. "
            f"Recomendacao: protocolar requerimento com PPP/LTCAT em anexo."
        )

    if tier == TIER_PROVA_MEDIA:
        return (
            f"PROVA MEDIA para '{nome_display}' (cargo: {cargo_display}). "
            f"O CBO, o setor economico e a jurisprudencia convergem para indicar "
            f"atividade especial, com agente(s) provavel(is): "
            f"{', '.join(agentes) if agentes else 'a confirmar'}. "
            f"POREM, ainda nao ha PPP/LTCAT confirmando a exposicao. "
            f"Proximo passo: solicitar PPP ao empregador para elevar a prova ao nivel maximo."
        )

    if tier == TIER_INDICIO_RELEVANTE:
        partes = [f"INDICIOS RELEVANTES para '{nome_display}' (cargo: {cargo_display})."]
        if flag_cbo_especial:
            partes.append(f"O CBO ({cbo}) indica funcao historicamente reconhecida como especial.")
        if flag_nome_match:
            partes.append("O nome do empregador corresponde a setor de risco.")
        partes.append(
            "Porem, faltam elementos para reconhecimento automatico. "
            "Documentos necessarios: " + "; ".join(docs_faltantes[:3]) if docs_faltantes else ""
        )
        return " ".join(partes)

    if tier == TIER_INDICIO_FRACO:
        return (
            f"INDICIO FRACO para '{nome_display}'. "
            f"Apenas o nome do empregador sugere possivel atividade de risco, "
            f"mas nao ha CBO confirmando, nem documentos comprobatorios. "
            f"Isso NAO e suficiente para reconhecimento. "
            f"Recomendacao: investigar a funcao real exercida, obter PPP e "
            f"verificar se o segurado esteve de fato exposto a agentes nocivos."
        )

    # TIER 5 - SEM LASTRO
    return (
        f"SEM LASTRO para '{nome_display}'. "
        f"Nenhum indicativo de atividade especial encontrado com base nos dados disponiveis. "
        f"Se o segurado alega exposicao a agentes nocivos neste vinculo, "
        f"solicitar PPP e outros documentos comprobatorios para nova analise."
    )
