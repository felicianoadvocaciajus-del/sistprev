"""
Análise automática de possibilidade de revisão para aposentados.

Quando o CNIS indica benefício ATIVO, analisa automaticamente se há
possibilidade de revisão e qual o impacto financeiro potencial.

Revisões analisadas:
  1. Revisão do Teto (EC 20/98 e EC 41/03)
  2. Revisão do Buraco Negro (DIB entre 05/10/1988 e 05/04/1991)
  3. Revisão do Art. 29, II (auxílio-doença convertido em aposentadoria)
  4. Revisão para inclusão de atividade especial não reconhecida
  5. Decadência (prazo de 10 anos — Art. 103 Lei 8.213/91)

NOTA: A Revisão da Vida Toda (Tema 1102 STF) foi DEFINITIVAMENTE ENCERRADA
pelo STF em 26/11/2025. ADIs 2.110 e 2.111 reverteram a tese.
Não cabe mais ação com base nessa revisão.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import List, Dict, Any, Optional


def analisar_possibilidade_revisao(
    dados_pessoais: Dict[str, Any],
    vinculos: List[Dict[str, Any]],
    beneficio: Dict[str, Any],
    der_base: date,
) -> Dict[str, Any]:
    """
    Analisa automaticamente todas as possibilidades de revisão.

    Args:
        dados_pessoais: nome, cpf, data_nascimento, sexo
        vinculos: lista de vínculos do CNIS
        beneficio: dados do benefício ativo (especie_codigo, data_inicio, situacao)
        der_base: data de referência para análise

    Returns:
        dict com análise de cada tipo de revisão e recomendação geral
    """
    resultado = {
        "beneficio_ativo": True,
        "especie": beneficio.get("especie", ""),
        "especie_codigo": beneficio.get("especie_codigo", 0),
        "data_concessao": beneficio.get("data_inicio"),
        "revisoes_possiveis": [],
        "recomendacao_geral": "",
        "total_revisoes_viaveis": 0,
    }

    dib = beneficio.get("data_inicio")
    if isinstance(dib, str):
        try:
            partes = dib.split("/")
            if len(partes) == 3:
                dib = date(int(partes[2]), int(partes[1]), int(partes[0]))
        except Exception:
            dib = None

    especie = beneficio.get("especie_codigo", 0)

    # ═══════════════════════════════════════════════════════════════════════
    # 1. DECADÊNCIA (Art. 103, Lei 8.213/91) — verificar primeiro
    # ═══════════════════════════════════════════════════════════════════════

    decadencia_ok = True
    prazo_decadencia = None
    if dib and isinstance(dib, date):
        prazo_decadencia = date(dib.year + 10, dib.month, dib.day)
        if der_base > prazo_decadencia:
            decadencia_ok = False

    resultado["decadencia"] = {
        "prazo_decenal": prazo_decadencia.strftime("%d/%m/%Y") if prazo_decadencia else None,
        "dentro_prazo": decadencia_ok,
        "mensagem": (
            f"Prazo decenal de revisão: até {prazo_decadencia.strftime('%d/%m/%Y')}. "
            + ("DENTRO do prazo — revisão é possível." if decadencia_ok else
               "FORA do prazo — revisão administrativa está decaída. Avaliar exceções judiciais (erro material, tese constitucional).")
        ),
        "fundamentacao": "Art. 103 da Lei 8.213/91 — prazo de 10 anos para revisão do ato de concessão.",
    }

    # ═══════════════════════════════════════════════════════════════════════
    # 2. REVISÃO DA VIDA TODA — ENCERRADA (Tema 1102 STF)
    # ═══════════════════════════════════════════════════════════════════════
    # O STF, em 21/03/2024 (ADIs 2.110 e 2.111), reverteu a decisão anterior
    # favorável ao segurado. Em 26/11/2025, nos Embargos de Declaração,
    # encerrou DEFINITIVAMENTE o Tema 1102 por 8x3.
    # A regra transitória da Lei 9.876/99 é de aplicação obrigatória.
    # NÃO cabe mais nenhuma ação nova com base nesta tese.
    # Modulação: valores recebidos até 05/04/2024 não precisam ser devolvidos.

    resultado["revisoes_possiveis"].append({
        "tipo": "Revisão da Vida Toda (ENCERRADA)",
        "aplicavel": False,
        "viavel": False,
        "fundamentacao": (
            "Tema 1102 STF — DEFINITIVAMENTE ENCERRADO em 26/11/2025. "
            "ADIs 2.110 e 2.111 (21/03/2024) reverteram a tese. "
            "Embargos de Declaração julgados em 26/11/2025 por 8x3."
        ),
        "analise": (
            "TESE ENCERRADA. O STF decidiu que a regra de transição da Lei 9.876/99 "
            "é de aplicação OBRIGATÓRIA. O segurado NÃO pode optar pelo cálculo que inclui "
            "contribuições anteriores a julho/1994. Não cabe mais ação judicial com base nesta tese. "
            "Modulação: valores já recebidos até 05/04/2024 não precisam ser devolvidos."
        ),
        "impacto_estimado": "NENHUM — tese encerrada pelo STF.",
        "prazo": "Encerrada definitivamente.",
        "documentos_necessarios": "N/A",
    })

    # ═══════════════════════════════════════════════════════════════════════
    # 3. REVISÃO DO TETO (EC 20/98 e EC 41/03)
    # ═══════════════════════════════════════════════════════════════════════

    teto_aplicavel = False
    teto_msg = ""
    if dib and isinstance(dib, date):
        if dib < date(2003, 12, 19):
            teto_aplicavel = True
            teto_msg = (
                "POSSÍVEL. O benefício foi concedido antes de dezembro/2003. "
                "Se o salário de benefício foi limitado ao teto na época, os reajustes "
                "das EC 20/98 (R$ 1.200,00 → R$ 1.328,25) e EC 41/03 (R$ 1.869,34 → R$ 2.400,00) "
                "devem ser aplicados proporcionalmente. Pode gerar diferenças significativas."
            )
        else:
            teto_msg = "NÃO APLICÁVEL — Benefício concedido após dezembro/2003. Teto já atualizado."

    resultado["revisoes_possiveis"].append({
        "tipo": "Revisão do Teto (EC 20/98 e EC 41/03)",
        "aplicavel": teto_aplicavel,
        "viavel": teto_aplicavel,  # Teto não está sujeito a decadência (tese do STF)
        "fundamentacao": "RE 564.354/SE — STF decidiu que o teto é aplicável de imediato, sem decadência.",
        "analise": teto_msg,
        "impacto_estimado": "ALTO para quem teve SB acima do teto na época da concessão.",
        "prazo": "Sem decadência — direito imprescritível (STF). Prescrição quinquenal dos atrasados.",
        "documentos_necessarios": "Carta de concessão original, processo administrativo do INSS.",
        "como_calcular_diferenca": (
            "1) Obter o Salário de Benefício (SB) original da carta de concessão. "
            "2) Verificar se o SB foi limitado ao teto vigente na DIB. "
            "3) Aplicar os novos tetos: EC 20/98 (R$ 1.200,00 para R$ 1.328,25) e EC 41/03 (R$ 2.400,00). "
            "4) Recalcular a RMI com o SB reajustado. "
            "5) A diferença mensal = RMI_revisada - RMI_atual. "
            "6) Atrasados = soma das diferenças mensais desde a vigência da EC, com correção INPC + juros SELIC."
        ),
    })

    # ═══════════════════════════════════════════════════════════════════════
    # 4. REVISÃO DO BURACO NEGRO
    # ═══════════════════════════════════════════════════════════════════════

    buraco_negro = False
    bn_msg = ""
    if dib and isinstance(dib, date):
        if date(1988, 10, 5) <= dib <= date(1991, 4, 5):
            buraco_negro = True
            bn_msg = (
                "POSSÍVEL. O benefício foi concedido no período do 'Buraco Negro' "
                "(05/10/1988 a 05/04/1991). A Lei 8.213/91, Art. 144, determinou a revisão "
                "de todos os benefícios concedidos nesse período. Se não foi revisado, "
                "pode haver diferenças significativas."
            )
        else:
            bn_msg = "NÃO APLICÁVEL — Benefício fora do período do Buraco Negro."

    resultado["revisoes_possiveis"].append({
        "tipo": "Revisão do Buraco Negro",
        "aplicavel": buraco_negro,
        "viavel": buraco_negro,
        "fundamentacao": "Art. 144, Lei 8.213/91 — revisão obrigatória de benefícios do período constitucional.",
        "analise": bn_msg,
        "impacto_estimado": "VARIÁVEL — depende da diferença entre cálculo original e revisado.",
        "prazo": "Direito adquirido — não há decadência para erro material.",
        "documentos_necessarios": "Carta de concessão, processo administrativo.",
        "como_calcular_diferenca": (
            "1) Obter a memória de cálculo original da concessão (antes da Lei 8.213/91). "
            "2) Recalcular pela regra definitiva do Art. 29 da Lei 8.213/91. "
            "3) A diferença mensal = RMI_recalculada - RMI_que_vem_sendo_paga. "
            "4) Atrasados incidem SOMENTE sobre a diferença mensal, não sobre o benefício integral."
        ),
    })

    # ═══════════════════════════════════════════════════════════════════════
    # 5. REVISÃO DO ART. 29, II (IRSM de fevereiro/94 — 39,67%)
    # ═══════════════════════════════════════════════════════════════════════

    art29_aplicavel = False
    art29_msg = ""
    if dib and isinstance(dib, date):
        if dib <= date(2012, 11, 21) and especie in (42, 41, 31, 91, 92, 32):
            art29_aplicavel = True
            art29_msg = (
                "POSSÍVEL. Benefício concedido antes de 21/11/2012. O INSS pode ter aplicado "
                "erroneamente o divisor mínimo (Art. 29, I em vez do II) no cálculo do salário de benefício, "
                "incluindo meses sem contribuição na média. A revisão pode aumentar a RMI."
            )
        else:
            art29_msg = "NÃO APLICÁVEL ao perfil deste benefício."

    resultado["revisoes_possiveis"].append({
        "tipo": "Revisão do Art. 29, II (Divisor Mínimo)",
        "aplicavel": art29_aplicavel,
        "viavel": art29_aplicavel and decadencia_ok,
        "fundamentacao": "Art. 29, II, Lei 8.213/91 — cálculo correto da média dos 80% maiores SC.",
        "analise": art29_msg,
        "impacto_estimado": "MODERADO a ALTO — especialmente para quem teve períodos sem contribuição no PBC.",
        "prazo": "Sujeito à decadência de 10 anos.",
        "documentos_necessarios": "CNIS, carta de concessão, processo administrativo.",
        "como_calcular_diferenca": (
            "1) Verificar se o INSS usou o divisor mínimo (60% do PBC) no cálculo. "
            "2) O correto é usar APENAS os 80% maiores salários de contribuição como divisor. "
            "3) Recalcular: média = soma dos 80% maiores SC / quantidade desses 80%. "
            "4) RMI_correta = média correta x coeficiente da espécie. "
            "5) Diferença mensal = RMI_correta - RMI_paga. "
            "6) Atrasados = soma das diferenças mensais (NÃO do benefício inteiro), corrigidas INPC + SELIC."
        ),
    })

    # ═══════════════════════════════════════════════════════════════════════
    # 6. REVISÃO POR ATIVIDADE ESPECIAL NÃO RECONHECIDA
    # ═══════════════════════════════════════════════════════════════════════

    resultado["revisoes_possiveis"].append({
        "tipo": "Revisão por Atividade Especial Não Reconhecida",
        "aplicavel": True,  # Sempre possível verificar
        "viavel": True,
        "fundamentacao": "Art. 57 e 58, Lei 8.213/91 — conversão de tempo especial em comum.",
        "analise": (
            "VERIFICAR. Se o segurado trabalhou em condições especiais (insalubridade, periculosidade, "
            "penosidade) e o tempo não foi computado com o fator de conversão, a revisão pode aumentar "
            "o tempo de contribuição e, consequentemente, a RMI. Aplicável mesmo para aposentados."
        ),
        "impacto_estimado": "ALTO — fator de conversão de 1.4 (homem) ou 1.2 (mulher) sobre o período especial.",
        "prazo": "Sem decadência para reconhecimento de tempo — apenas prescrição quinquenal dos valores.",
        "documentos_necessarios": "PPP (Perfil Profissiográfico Previdenciário), LTCAT, laudo técnico.",
        "como_calcular_diferenca": (
            "1) Identificar períodos especiais não reconhecidos pelo INSS. "
            "2) Aplicar fator de conversão: 1.4 (homem 25 anos) ou 1.2 (mulher 25 anos). "
            "3) Recalcular o TC total com a conversão. "
            "4) Recalcular a RMI com o novo TC (pode alterar coeficiente e/ou fator previdenciário). "
            "5) Diferença mensal = RMI_nova - RMI_atual. "
            "6) Atrasados = soma das diferenças mensais desde a DIB (limitado à prescrição 5 anos)."
        ),
    })

    # ═══════════════════════════════════════════════════════════════════════
    # RECOMENDAÇÃO GERAL
    # ═══════════════════════════════════════════════════════════════════════

    viaveis = [r for r in resultado["revisoes_possiveis"] if r.get("viavel")]
    resultado["total_revisoes_viaveis"] = len(viaveis)

    if not viaveis:
        resultado["recomendacao_geral"] = (
            "Nenhuma revisão automaticamente identificada como viável. "
            "Recomenda-se análise manual detalhada do processo administrativo de concessão."
        )
    elif len(viaveis) == 1:
        resultado["recomendacao_geral"] = (
            f"Foi identificada 1 possibilidade de revisão: {viaveis[0]['tipo']}. "
            f"Recomenda-se análise aprofundada para confirmar viabilidade e estimar impacto financeiro."
        )
    else:
        tipos = ", ".join([v["tipo"] for v in viaveis[:3]])
        resultado["recomendacao_geral"] = (
            f"Foram identificadas {len(viaveis)} possibilidades de revisão: {tipos}. "
            f"Recomenda-se priorizar as revisões com maior impacto estimado e verificar documentação necessária."
        )

    return resultado
