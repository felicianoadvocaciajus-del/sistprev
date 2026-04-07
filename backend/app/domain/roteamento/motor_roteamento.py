"""
Motor de Roteamento de Caso Previdenciario.

Analisa dados do segurado, beneficios do CNIS, carta de concessao e vinculos
especiais para determinar automaticamente o modo de operacao correto.

Hierarquia de decisao (em ordem de prioridade):
  1. Beneficio ativo (aposentadoria ativa, beneficio em manutencao) -> REVISAO
  2. Carta de concessao presente -> REVISAO
  3. Dados HISCAL/HISCRE presentes -> REVISAO
  4. Beneficio indeferido -> REANALISE_INDEFERIDO
  5. Indicadores de atividade especial -> ATIVIDADE_ESPECIAL
  6. Tempo de acordo internacional -> ACORDO_INTERNACIONAL
  7. Nenhum dos acima -> NOVO_BENEFICIO
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class ModoRecomendado(str, Enum):
    REVISAO = "REVISAO"
    NOVO_BENEFICIO = "NOVO_BENEFICIO"
    REANALISE_INDEFERIDO = "REANALISE_INDEFERIDO"
    ATIVIDADE_ESPECIAL = "ATIVIDADE_ESPECIAL"
    ACORDO_INTERNACIONAL = "ACORDO_INTERNACIONAL"
    TRIAGEM_DOCUMENTAL = "TRIAGEM_DOCUMENTAL"


# Codigos de especie de aposentadorias (beneficios definitivos)
_ESPECIES_APOSENTADORIA = {41, 42, 46, 57, 32, 92}

# Codigos de especie de auxilios por incapacidade
_ESPECIES_AUXILIO = {31, 91, 36}

# Codigos de especie que indicam beneficio em manutencao
_ESPECIES_BENEFICIO_MANUTENCAO = _ESPECIES_APOSENTADORIA | _ESPECIES_AUXILIO | {21, 22, 25, 80, 87, 88}

# Palavras-chave que indicam acordo internacional nos vinculos
_PALAVRAS_ACORDO_INTERNACIONAL = [
    "acordo internacional", "convenio internacional", "tempo exterior",
    "portugal", "espanha", "italia", "japao", "japão", "alemanha",
    "franca", "frança", "belgica", "bélgica", "cabo verde",
    "grecia", "grécia", "luxemburgo", "chile", "mercosul",
    "tempo no exterior", "contribuicao exterior", "contribuição exterior",
]


def rotear_caso(
    segurado_data: Dict[str, Any],
    beneficios: Optional[List[Dict[str, Any]]] = None,
    carta_concessao: Optional[Dict[str, Any]] = None,
    vinculos_especiais: Optional[List[Dict[str, Any]]] = None,
    hiscal_hiscre: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Motor principal de roteamento de caso.

    Args:
        segurado_data: Dados do segurado (schema SeguradoSchema serializado).
        beneficios: Lista de beneficios detectados do CNIS.
        carta_concessao: Dados extraidos da carta de concessao (opcional).
        vinculos_especiais: Lista de vinculos com indicacao de atividade especial.
        hiscal_hiscre: Dados HISCAL/HISCRE extraidos (opcional).

    Returns:
        Dict JSON-serializavel com o resultado do roteamento.
    """
    beneficios = beneficios or []
    vinculos_especiais = vinculos_especiais or []

    # Estado acumulado durante a analise
    motivos: List[str] = []
    alertas: List[str] = []
    conflitos: List[str] = []
    documentos_faltantes: List[str] = []
    revisoes_detectadas: List[Dict[str, Any]] = []
    dados_pre_preenchidos: Dict[str, Any] = {}
    confianca = 0.0
    modo = ModoRecomendado.NOVO_BENEFICIO

    # -------------------------------------------------------------------------
    # Extrair informacoes basicas do segurado
    # -------------------------------------------------------------------------
    dp = segurado_data.get("dados_pessoais", {})
    vinculos = segurado_data.get("vinculos", [])
    beneficios_anteriores = segurado_data.get("beneficios_anteriores", [])
    nome = dp.get("nome", "")
    sexo = dp.get("sexo", "")
    data_nascimento = dp.get("data_nascimento", "")

    if nome:
        dados_pre_preenchidos["nome_segurado"] = nome
    if sexo:
        dados_pre_preenchidos["sexo"] = sexo
    if data_nascimento:
        dados_pre_preenchidos["data_nascimento"] = data_nascimento
    if dp.get("cpf"):
        dados_pre_preenchidos["cpf"] = dp["cpf"]
    if dp.get("nit"):
        dados_pre_preenchidos["nit"] = dp["nit"]

    # -------------------------------------------------------------------------
    # 1. Verificar beneficio ativo (aposentadoria ativa / beneficio em manutencao)
    # -------------------------------------------------------------------------
    beneficio_ativo_info = _detectar_beneficio_ativo(beneficios, beneficios_anteriores)

    if beneficio_ativo_info:
        modo = ModoRecomendado.REVISAO
        confianca = max(confianca, 0.90)
        motivos.append(
            f"Beneficio ativo detectado: especie {beneficio_ativo_info.get('especie', '?')} "
            f"(NB: {beneficio_ativo_info.get('nb', 'nao informado')}), "
            f"DIB: {beneficio_ativo_info.get('dib', '?')}. "
            f"Modo REVISAO e o padrao para beneficios em manutencao."
        )

        # Pre-preencher dados do beneficio
        dados_pre_preenchidos["beneficio_ativo"] = True
        if beneficio_ativo_info.get("nb"):
            dados_pre_preenchidos["numero_beneficio"] = beneficio_ativo_info["nb"]
        if beneficio_ativo_info.get("dib"):
            dados_pre_preenchidos["dib"] = beneficio_ativo_info["dib"]
        if beneficio_ativo_info.get("rmi"):
            dados_pre_preenchidos["rmi_atual"] = beneficio_ativo_info["rmi"]

        # Verificar decadencia
        _verificar_decadencia(beneficio_ativo_info, alertas, revisoes_detectadas)

        # Documentos recomendados para revisao
        if "Carta de concessao" not in [d.split(" (")[0] for d in documentos_faltantes]:
            documentos_faltantes.append(
                "Carta de concessao (essencial para revisao — contem SB, coeficiente, fator previdenciario)"
            )
        documentos_faltantes.append("Processo administrativo do INSS (PA)")
        documentos_faltantes.append("HISCRE/HISCAL (historico de creditos/salarios)")

    # -------------------------------------------------------------------------
    # 2. Verificar carta de concessao
    # -------------------------------------------------------------------------
    if carta_concessao and carta_concessao.get("sucesso", False):
        if modo != ModoRecomendado.REVISAO:
            modo = ModoRecomendado.REVISAO
            confianca = max(confianca, 0.85)
        else:
            confianca = max(confianca, 0.95)

        motivos.append(
            "Carta de concessao uploadada. Modo REVISAO confirmado — "
            "carta permite recalcular e comparar RMI original vs. correta."
        )

        # Extrair dados da carta para pre-preencher
        cc = carta_concessao
        if cc.get("numero_beneficio"):
            dados_pre_preenchidos["numero_beneficio"] = cc["numero_beneficio"]
        if cc.get("especie"):
            dados_pre_preenchidos["especie_beneficio"] = cc["especie"]
        if cc.get("dib"):
            dados_pre_preenchidos["dib"] = cc["dib"]
        if cc.get("rmi"):
            dados_pre_preenchidos["rmi_carta"] = cc["rmi"]
        if cc.get("salario_beneficio"):
            dados_pre_preenchidos["salario_beneficio_carta"] = cc["salario_beneficio"]
        if cc.get("fator_previdenciario"):
            dados_pre_preenchidos["fator_previdenciario_carta"] = cc["fator_previdenciario"]
        if cc.get("coeficiente"):
            dados_pre_preenchidos["coeficiente_carta"] = cc["coeficiente"]

        # Se temos carta mas nao temos beneficio ativo nos dados do CNIS, criar info
        if not beneficio_ativo_info:
            beneficio_ativo_info = {
                "nb": cc.get("numero_beneficio", ""),
                "especie": cc.get("especie", ""),
                "dib": cc.get("dib", ""),
                "rmi": cc.get("rmi", ""),
            }

        # Validar consistencia entre carta e CNIS
        if beneficio_ativo_info and cc.get("numero_beneficio"):
            nb_carta = cc.get("numero_beneficio", "").strip()
            nb_cnis = str(beneficio_ativo_info.get("nb", "")).strip()
            if nb_cnis and nb_carta and nb_cnis != nb_carta:
                conflitos.append(
                    f"Numero do beneficio divergente: CNIS={nb_cnis}, Carta={nb_carta}. "
                    f"Verificar qual e o correto."
                )

    # -------------------------------------------------------------------------
    # 3. Verificar dados HISCAL/HISCRE
    # -------------------------------------------------------------------------
    if hiscal_hiscre:
        if modo != ModoRecomendado.REVISAO:
            modo = ModoRecomendado.REVISAO
            confianca = max(confianca, 0.85)
        else:
            confianca = max(confianca, 0.95)

        motivos.append(
            "Dados HISCAL/HISCRE detectados. Modo REVISAO — "
            "historico de creditos permite verificar erros no calculo do INSS."
        )

        if hiscal_hiscre.get("competencias"):
            dados_pre_preenchidos["hiscre_competencias"] = len(hiscal_hiscre["competencias"])

    # -------------------------------------------------------------------------
    # 4. Verificar beneficio indeferido
    # -------------------------------------------------------------------------
    indeferido_info = _detectar_indeferido(beneficios)

    if indeferido_info:
        # Indeferido so prevalece se nao ha beneficio ativo
        if modo != ModoRecomendado.REVISAO:
            modo = ModoRecomendado.REANALISE_INDEFERIDO
            confianca = max(confianca, 0.80)

        motivos.append(
            f"Beneficio indeferido detectado: especie {indeferido_info.get('especie', '?')}, "
            f"data: {indeferido_info.get('data_inicio', '?')}. "
            f"Recomendado REANALISE para verificar se requisitos foram atingidos posteriormente."
        )

        dados_pre_preenchidos["indeferido"] = True
        dados_pre_preenchidos["especie_indeferido"] = indeferido_info.get("especie", "")

        documentos_faltantes.append("Carta de indeferimento do INSS (com motivo da negativa)")
        documentos_faltantes.append("Cumprimento de exigencia (se aplicavel)")

        alertas.append(
            "Beneficio indeferido encontrado. Verificar: (1) se os requisitos ja foram atingidos, "
            "(2) se houve erro do INSS no indeferimento, (3) prazo para recurso administrativo."
        )

    # -------------------------------------------------------------------------
    # 5. Verificar atividade especial
    # -------------------------------------------------------------------------
    especial_detectada = _detectar_atividade_especial(vinculos, vinculos_especiais)

    if especial_detectada:
        # Atividade especial so prevalece se nao ha revisao nem indeferido
        if modo == ModoRecomendado.NOVO_BENEFICIO:
            modo = ModoRecomendado.ATIVIDADE_ESPECIAL
            confianca = max(confianca, 0.75)
        elif modo == ModoRecomendado.REVISAO:
            # Em revisao, atividade especial e um plus
            confianca = min(confianca + 0.03, 1.0)

        motivos.append(
            f"Atividade especial detectada em {especial_detectada['total']} vinculo(s). "
            f"Tipos: {', '.join(especial_detectada['tipos'])}. "
            f"Conversao de tempo especial pode aumentar TC e/ou RMI."
        )

        dados_pre_preenchidos["tem_atividade_especial"] = True
        dados_pre_preenchidos["vinculos_especiais_count"] = especial_detectada["total"]

        if not any("PPP" in d for d in documentos_faltantes):
            documentos_faltantes.append(
                "PPP (Perfil Profissiografico Previdenciario) de cada empregador com atividade especial"
            )
            documentos_faltantes.append("LTCAT (Laudo Tecnico de Condicoes Ambientais do Trabalho)")

        alertas.append(
            "Atividade especial identificada. O fator de conversao (1.4 homem / 1.2 mulher para 25 anos) "
            "pode antecipar a aposentadoria ou aumentar o valor do beneficio."
        )

    # -------------------------------------------------------------------------
    # 6. Verificar acordo internacional
    # -------------------------------------------------------------------------
    acordo_detectado = _detectar_acordo_internacional(vinculos, segurado_data)

    if acordo_detectado:
        if modo == ModoRecomendado.NOVO_BENEFICIO:
            modo = ModoRecomendado.ACORDO_INTERNACIONAL
            confianca = max(confianca, 0.70)
        elif modo in (ModoRecomendado.REVISAO, ModoRecomendado.ATIVIDADE_ESPECIAL):
            confianca = min(confianca + 0.02, 1.0)

        motivos.append(
            f"Indicadores de acordo internacional detectados: {acordo_detectado['descricao']}. "
            f"Tempo no exterior pode ser somado ao tempo brasileiro."
        )

        dados_pre_preenchidos["tem_acordo_internacional"] = True

        documentos_faltantes.append("Formulario de ligacao do pais de origem")
        documentos_faltantes.append("Comprovante de tempo de servico no exterior")

        alertas.append(
            "Acordo internacional detectado. Verificar se o pais tem convenio vigente com o Brasil "
            "e se a documentacao estrangeira esta devidamente apostilada/consularizada."
        )

    # -------------------------------------------------------------------------
    # 7. Se nenhuma regra foi acionada -> NOVO_BENEFICIO ou TRIAGEM
    # -------------------------------------------------------------------------
    if not motivos:
        # Verificar se ha dados suficientes para qualquer analise
        if not vinculos and not beneficios and not beneficios_anteriores:
            modo = ModoRecomendado.TRIAGEM_DOCUMENTAL
            confianca = 0.30
            motivos.append(
                "Dados insuficientes para roteamento automatico. "
                "Nenhum vinculo, beneficio ou documento detectado. "
                "Recomendado upload do CNIS para iniciar a analise."
            )
            documentos_faltantes.append("CNIS (Cadastro Nacional de Informacoes Sociais) — documento principal")
            documentos_faltantes.append("RG ou CNH do segurado")
        else:
            modo = ModoRecomendado.NOVO_BENEFICIO
            confianca = 0.70
            motivos.append(
                "Nenhum beneficio ativo ou indeferido detectado. "
                "Segurado aparenta nao ter beneficio concedido. "
                "Modo NOVO_BENEFICIO para calcular elegibilidade e projetar datas."
            )
            documentos_faltantes.append("Carteira de trabalho (CTPS) para cruzamento com CNIS")

    # -------------------------------------------------------------------------
    # Detectar conflitos nos dados
    # -------------------------------------------------------------------------
    conflitos.extend(_detectar_conflitos(segurado_data, beneficios, carta_concessao))

    # -------------------------------------------------------------------------
    # Detectar revisoes anteriores
    # -------------------------------------------------------------------------
    revisoes_detectadas.extend(_detectar_revisoes_anteriores(beneficios, beneficios_anteriores))

    # -------------------------------------------------------------------------
    # Remover documentos duplicados
    # -------------------------------------------------------------------------
    documentos_faltantes = list(dict.fromkeys(documentos_faltantes))

    # -------------------------------------------------------------------------
    # Montar resultado final
    # -------------------------------------------------------------------------
    return {
        "modo_recomendado": modo.value,
        "confianca": round(confianca, 2),
        "motivos": motivos,
        "beneficio_ativo": beneficio_ativo_info or {},
        "revisoes_anteriores_detectadas": revisoes_detectadas,
        "documentos_faltantes": documentos_faltantes,
        "alertas": alertas,
        "dados_pre_preenchidos": dados_pre_preenchidos,
        "conflitos_detectados": conflitos,
    }


# =============================================================================
# Funcoes auxiliares de deteccao
# =============================================================================

def _detectar_beneficio_ativo(
    beneficios: List[Dict[str, Any]],
    beneficios_anteriores: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Detecta beneficio ativo (em manutencao) nos dados do CNIS."""
    # Primeiro: buscar nos beneficios do CNIS (campo 'situacao' == 'ATIVO')
    for b in beneficios:
        situacao = str(b.get("situacao", "")).upper()
        if situacao in ("ATIVO", "ATIVA", "EM MANUTENCAO", "EM MANUTENÇÃO"):
            especie_cod = b.get("especie_codigo", 0)
            if isinstance(especie_cod, str):
                try:
                    especie_cod = int(especie_cod)
                except ValueError:
                    especie_cod = 0
            return {
                "nb": b.get("nb", b.get("numero_beneficio", "")),
                "especie": b.get("especie", ""),
                "especie_codigo": especie_cod,
                "dib": b.get("data_inicio", ""),
                "dcb": b.get("data_fim"),
                "rmi": b.get("rmi", ""),
                "situacao": situacao,
            }

    # Segundo: buscar nos beneficios_anteriores (campo 'dcb' == None significa ativo)
    for b in beneficios_anteriores:
        dcb = b.get("dcb")
        if not dcb or str(dcb).strip() == "":
            return {
                "nb": b.get("numero_beneficio", ""),
                "especie": b.get("especie", ""),
                "especie_codigo": 0,
                "dib": b.get("dib", ""),
                "dcb": None,
                "rmi": b.get("rmi", "0"),
                "situacao": "ATIVO",
            }

    return None


def _detectar_indeferido(
    beneficios: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Detecta beneficio indeferido nos dados do CNIS."""
    for b in beneficios:
        situacao = str(b.get("situacao", "")).upper()
        if situacao in ("INDEFERIDO", "CESSADO", "SUSPENSO", "CESSADA", "SUSPENSA"):
            return {
                "especie": b.get("especie", ""),
                "especie_codigo": b.get("especie_codigo", 0),
                "data_inicio": b.get("data_inicio", ""),
                "situacao": situacao,
                "nb": b.get("nb", b.get("numero_beneficio", "")),
            }
    return None


def _detectar_atividade_especial(
    vinculos: List[Dict[str, Any]],
    vinculos_especiais: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Detecta vinculos com atividade especial."""
    especiais = []
    tipos_set = set()

    # Dos vinculos do segurado
    for v in vinculos:
        tipo_ativ = str(v.get("tipo_atividade", "NORMAL")).upper()
        if tipo_ativ != "NORMAL" and tipo_ativ.startswith("ESPECIAL"):
            especiais.append(v)
            tipos_set.add(tipo_ativ)

    # Dos vinculos especiais informados separadamente (ex: analise CTPS/PPP)
    for v in vinculos_especiais:
        especial_info = v.get("especial", {})
        if especial_info.get("possivel", False):
            especiais.append(v)
            prob = especial_info.get("probabilidade", "")
            tipo = especial_info.get("via", "desconhecido")
            tipos_set.add(f"POSSIVEL_{prob}_{tipo}".upper())

    if especiais:
        return {
            "total": len(especiais),
            "tipos": list(tipos_set) if tipos_set else ["ESPECIAL"],
            "vinculos": especiais,
        }

    return None


def _detectar_acordo_internacional(
    vinculos: List[Dict[str, Any]],
    segurado_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Detecta indicadores de acordo internacional."""
    descricoes = []

    # Verificar observacoes dos vinculos
    for v in vinculos:
        obs = str(v.get("observacao", "") or "").lower()
        indicadores = str(v.get("indicadores", "") or "").lower()
        empregador = str(v.get("empregador_nome", "") or "").lower()

        texto_completo = f"{obs} {indicadores} {empregador}"

        for palavra in _PALAVRAS_ACORDO_INTERNACIONAL:
            if palavra in texto_completo:
                nome_emp = v.get("empregador_nome", "desconhecido")
                descricoes.append(f"Vinculo '{nome_emp}' com indicador: '{palavra}'")
                break

    # Verificar observacoes do segurado
    obs_segurado = str(segurado_data.get("observacoes", "") or "").lower()
    for palavra in _PALAVRAS_ACORDO_INTERNACIONAL:
        if palavra in obs_segurado:
            descricoes.append(f"Observacao do segurado menciona: '{palavra}'")
            break

    if descricoes:
        return {
            "descricao": "; ".join(descricoes[:3]),
            "total_indicadores": len(descricoes),
        }

    return None


def _verificar_decadencia(
    beneficio_info: Dict[str, Any],
    alertas: List[str],
    revisoes: List[Dict[str, Any]],
) -> None:
    """Verifica prazo de decadencia e adiciona alertas se necessario."""
    dib_str = beneficio_info.get("dib", "")
    if not dib_str:
        alertas.append(
            "DIB nao informada — impossivel calcular prazo de decadencia. "
            "Verificar carta de concessao."
        )
        return

    dib = _parse_date_safe(dib_str)
    if not dib:
        return

    hoje = date.today()
    try:
        prazo = date(dib.year + 10, dib.month, dib.day)
    except ValueError:
        # 29/02 em ano nao bissexto
        prazo = date(dib.year + 10, dib.month, 28)

    if hoje > prazo:
        alertas.append(
            f"ATENCAO: Prazo de decadencia possivelmente expirado. "
            f"DIB: {dib.strftime('%d/%m/%Y')}, prazo decenal: {prazo.strftime('%d/%m/%Y')}. "
            f"Verificar excecoes: erro material, tese constitucional (RE 564.354 — teto nao decai)."
        )
        revisoes.append({
            "tipo": "DECADENCIA",
            "descricao": f"Prazo decenal expirado em {prazo.strftime('%d/%m/%Y')}",
            "impacto": "Revisao administrativa bloqueada. Avaliar via judicial.",
        })
    else:
        dias_restantes = (prazo - hoje).days
        if dias_restantes < 365:
            alertas.append(
                f"URGENTE: Prazo de decadencia expira em {prazo.strftime('%d/%m/%Y')} "
                f"({dias_restantes} dias restantes). Agir imediatamente."
            )
        elif dias_restantes < 730:
            alertas.append(
                f"Prazo de decadencia em {prazo.strftime('%d/%m/%Y')} "
                f"({dias_restantes} dias restantes). Planejar revisao."
            )


def _detectar_conflitos(
    segurado_data: Dict[str, Any],
    beneficios: List[Dict[str, Any]],
    carta_concessao: Optional[Dict[str, Any]],
) -> List[str]:
    """Detecta inconsistencias nos dados fornecidos."""
    conflitos = []

    vinculos = segurado_data.get("vinculos", [])

    # Verificar vinculos sobrepostos
    for i, v1 in enumerate(vinculos):
        di1 = _parse_date_safe(v1.get("data_inicio", ""))
        df1 = _parse_date_safe(v1.get("data_fim", ""))
        if not di1:
            continue
        for v2 in vinculos[i + 1:]:
            di2 = _parse_date_safe(v2.get("data_inicio", ""))
            df2 = _parse_date_safe(v2.get("data_fim", ""))
            if not di2:
                continue
            # Verificar sobreposicao
            fim1 = df1 or date.today()
            fim2 = df2 or date.today()
            if di1 <= fim2 and di2 <= fim1:
                emp1 = v1.get("empregador_nome", "?")
                emp2 = v2.get("empregador_nome", "?")
                conflitos.append(
                    f"Vinculos sobrepostos: '{emp1}' ({v1.get('data_inicio', '?')}) "
                    f"e '{emp2}' ({v2.get('data_inicio', '?')}). "
                    f"Verificar concomitancia — pode ser permitida ou indicar erro no CNIS."
                )

    # Verificar se ha beneficio ativo mas nenhum vinculo encerrado
    ativos = [b for b in beneficios if str(b.get("situacao", "")).upper() in ("ATIVO", "ATIVA")]
    if ativos:
        vinculos_abertos = [v for v in vinculos if not v.get("data_fim")]
        if vinculos_abertos:
            conflitos.append(
                "Beneficio ativo com vinculo em aberto. Verificar se o segurado "
                "ainda esta trabalhando (pode afetar o tipo de revisao)."
            )

    # Verificar datas futuras em vinculos
    hoje = date.today()
    for v in vinculos:
        di = _parse_date_safe(v.get("data_inicio", ""))
        if di and di > hoje:
            conflitos.append(
                f"Vinculo com data de inicio futura: {v.get('empregador_nome', '?')} "
                f"em {v.get('data_inicio', '?')}. Possivel erro de parsing."
            )

    return conflitos


def _detectar_revisoes_anteriores(
    beneficios: List[Dict[str, Any]],
    beneficios_anteriores: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detecta eventos de revisao ja ocorridos."""
    revisoes = []

    # Beneficios cessados seguidos de novos podem indicar revisao/transformacao
    cessados = []
    ativos = []

    for b in beneficios:
        sit = str(b.get("situacao", "")).upper()
        if sit in ("ATIVO", "ATIVA"):
            ativos.append(b)
        elif sit in ("CESSADO", "CESSADA"):
            cessados.append(b)

    # Se ha cessado + ativo da mesma especie, pode ser revisao
    for c in cessados:
        esp_c = c.get("especie_codigo", 0)
        for a in ativos:
            esp_a = a.get("especie_codigo", 0)
            if esp_c == esp_a:
                revisoes.append({
                    "tipo": "TRANSFORMACAO",
                    "descricao": (
                        f"Beneficio especie {esp_c} cessado e reaberto. "
                        f"Possivel revisao ou transformacao anterior."
                    ),
                    "beneficio_cessado": c.get("data_inicio", ""),
                    "beneficio_ativo": a.get("data_inicio", ""),
                })

    # Se ha auxilio-doenca cessado seguido de aposentadoria, e conversao
    for c in cessados:
        esp_c = _safe_int(c.get("especie_codigo", 0))
        if esp_c in (31, 91):
            for a in ativos:
                esp_a = _safe_int(a.get("especie_codigo", 0))
                if esp_a in _ESPECIES_APOSENTADORIA:
                    revisoes.append({
                        "tipo": "CONVERSAO_AUXILIO_APOSENTADORIA",
                        "descricao": (
                            f"Auxilio-doenca (especie {esp_c}) convertido em "
                            f"aposentadoria (especie {esp_a}). Verificar Art. 29, II."
                        ),
                        "auxilio_cessado": c.get("data_inicio", ""),
                        "aposentadoria_ativa": a.get("data_inicio", ""),
                    })

    return revisoes


# =============================================================================
# Utilidades
# =============================================================================

def _parse_date_safe(valor: Any) -> Optional[date]:
    """Tenta parsear uma data de forma segura, retornando None em caso de falha."""
    if isinstance(valor, date):
        return valor
    if not valor or not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not valor:
        return None
    try:
        # Formato DD/MM/AAAA
        partes = valor.split("/")
        if len(partes) == 3:
            return date(int(partes[2]), int(partes[1]), int(partes[0]))
    except (ValueError, IndexError):
        pass
    try:
        # Formato ISO AAAA-MM-DD
        partes = valor.split("-")
        if len(partes) == 3:
            return date(int(partes[0]), int(partes[1]), int(partes[2]))
    except (ValueError, IndexError):
        pass
    return None


def _safe_int(valor: Any) -> int:
    """Converte para int de forma segura."""
    if isinstance(valor, int):
        return valor
    try:
        return int(valor)
    except (ValueError, TypeError):
        return 0
