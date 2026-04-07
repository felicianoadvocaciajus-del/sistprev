"""
Planejamento Previdenciário — Projeção de Datas de Aposentadoria.

Para cada regra de transição (EC 103/2019) e regra permanente,
calcula a data EXATA em que o segurado se tornará elegível,
considerando contribuição contínua a partir de hoje.

Método:
  Itera mês a mês (DER simulada), chamando comparar_todas() para
  cada data futura, até encontrar a data em que cada regra vira elegível.
  Limite máximo: 40 anos à frente.

Retorna para cada regra:
  - data_elegibilidade: quando se torna elegível
  - anos_meses_faltantes: "X anos e Y meses"
  - rmi_projetada: RMI estimada naquela data (com salário atual)
  - recomendacao: qual a melhor estratégia
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from ..models.segurado import Segurado
from ..models.vinculo import Vinculo
from ..models.contribuicao import Contribuicao
from ..transicao.comparador import comparar_todas
from ..indices.teto_previdenciario import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data
from ..tempo.contagem import calcular_tempo_contribuicao, calcular_carencia


def calcular_planejamento(
    segurado: Segurado,
    der_base: date,
    salario_projetado: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Projeta as datas de aposentadoria para cada regra.

    Args:
        segurado: dados completos do segurado
        der_base: data de hoje (referência)
        salario_projetado: salário mensal para contribuições futuras
                           (usa a média atual se não informado)

    Returns:
        dict com projeções por regra + melhor estratégia + resumo
    """
    # Salário para contribuições futuras
    sal = salario_projetado or _media_salario_atual(segurado, der_base)

    # Projetar mês a mês (até 480 meses = 40 anos)
    projecoes: Dict[str, Dict] = {}
    melhor_data: Optional[date] = None
    melhor_regra_nome: Optional[str] = None
    melhor_rmi = Decimal("0")

    # Estratégia: criar blocos anuais de contribuições ao invés de uma por mês.
    # Isso mantém a lista de contribuições pequena (≤40 entradas para 40 anos).
    # Precisão: ±1 mês (verificamos mês a mês dentro do ano de elegibilidade).
    from copy import deepcopy

    der_simulada = _inicio_proximo_mes(der_base)

    # Fase 1: avança ano a ano até encontrar o ano de elegibilidade de cada regra
    for ano_idx in range(1, 41):
        seg_ano = deepcopy(segurado)
        # Adiciona um vínculo futuro com 12 competências × ano_idx anos
        _adicionar_bloco_anual(seg_ano, der_base, sal, ano_idx * 12)
        der_ano = _avancar_meses(der_base, ano_idx * 12)

        cenarios = comparar_todas(seg_ano, der_ano)
        for cenario in cenarios:
            nome = cenario.nome_regra
            if nome in projecoes:
                continue
            if cenario.elegivel:
                # Fase 2: refina mês a mês dentro do ano anterior
                mes_inicio = (ano_idx - 1) * 12 + 1
                mes_fim = ano_idx * 12
                for mes in range(mes_inicio, mes_fim + 1):
                    seg_mes = deepcopy(segurado)
                    _adicionar_bloco_anual(seg_mes, der_base, sal, mes)
                    der_mes = _avancar_meses(der_base, mes)
                    cenarios_mes = comparar_todas(seg_mes, der_mes)
                    c_mes = next((c for c in cenarios_mes if c.nome_regra == nome and c.elegivel), None)
                    if c_mes:
                        anos_f, meses_r = divmod(mes, 12)
                        projecoes[nome] = {
                            "regra": nome,
                            "base_legal": c_mes.base_legal,
                            "data_elegibilidade": der_mes,
                            "meses_faltantes": mes,
                            "anos_faltantes": anos_f,
                            "meses_resto": meses_r,
                            "texto_faltante": _formatar_periodo(anos_f, meses_r),
                            "rmi_projetada": c_mes.rmi_teto,
                            "rmi_formatada": c_mes.rmi_formatada,
                            "salario_beneficio": c_mes.salario_beneficio,
                            "coeficiente": c_mes.coeficiente,
                            "fator_previdenciario": c_mes.fator_previdenciario,
                            "tc_na_data": c_mes.tempo_contribuicao,
                            "mensagem_cliente": _mensagem_cliente(nome, anos_f, meses_r, der_mes, c_mes.rmi_teto),
                        }
                        if melhor_data is None or der_mes < melhor_data or (
                            der_mes == melhor_data and c_mes.rmi_teto > melhor_rmi
                        ):
                            melhor_data = der_mes
                            melhor_regra_nome = nome
                            melhor_rmi = c_mes.rmi_teto
                        break

        if len(projecoes) >= 6:
            break

    # Regras sem projecao (nao alcancaveis em 40 anos)
    # Nomes dependem do regime temporal
    from ..constantes import DatasCorte as _DC
    if der_base < _DC.EC_103_2019:
        todos_nomes = [
            "Aposentadoria por TC + Fator Previdenciario (Lei 8.213/91)",
            "Regra 85/95 — Afasta FP (Art. 29-C Lei 8.213/91)",
            "Aposentadoria por Idade (Lei 8.213/91 Art. 48)",
        ]
    else:
        todos_nomes = [
            "Transição — Sistema de Pontos (Art. 15 EC 103/2019)",
            "Transição — Idade Mínima Progressiva (Art. 16 EC 103/2019)",
            "Transição — Pedágio 50% + FP (Art. 17 EC 103/2019)",
            "Transição — Pedágio 100% + Idade Mínima (Art. 20 EC 103/2019)",
            "Direito Adquirido — TC completo antes de 13/11/2019",
            "Aposentadoria por Idade (Regra Permanente EC 103)",
        ]
    for nome in todos_nomes:
        if nome not in projecoes:
            projecoes[nome] = {
                "regra": nome,
                "data_elegibilidade": None,
                "meses_faltantes": None,
                "texto_faltante": "Não alcançável",
                "rmi_projetada": Decimal("0"),
                "rmi_formatada": "—",
                "mensagem_cliente": "Esta regra não se aplica ao seu perfil.",
            }

    # Situação atual (sem contribuições futuras)
    cenarios_hoje = comparar_todas(segurado, der_base)
    elegiveis_hoje = [c for c in cenarios_hoje if c.elegivel]

    # TC atual
    tc_atual = calcular_tempo_contribuicao(
        segurado.vinculos, der_base, segurado.sexo,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )

    # Novas análises
    qualidade = _analisar_qualidade_segurado(segurado, der_base)
    pensao = _projetar_pensao(segurado, der_base, melhor_rmi)
    cenarios = _cenarios_vida_quantificados(segurado, der_base, projecoes, sal)
    plano = _gerar_plano_acao(segurado, der_base, projecoes, qualidade)

    # Carência (contribuições efetivas)
    carencia_meses = calcular_carencia(
        segurado.vinculos, der_base,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )

    # Calcular TC SEM B31 (para comparação)
    tc_sem_b31 = calcular_tempo_contribuicao(
        segurado.vinculos, der_base, segurado.sexo,
        beneficios_anteriores=None,  # SEM B31
    )

    # Dias de B31 intercalado
    dias_b31 = tc_atual.dias_total - tc_sem_b31.dias_total

    # Meses faltantes de carência
    carencia_exigida = 180
    faltam_carencia = max(0, carencia_exigida - carencia_meses)

    tc_info = {
        "anos": tc_atual.anos,
        "meses": tc_atual.meses_restantes,
        "dias": tc_atual.dias_restantes,
        "total_dias": tc_atual.dias_total,
    }

    # Análise TC vs Carência (para demonstrar no frontend)
    analise_tc_carencia = {
        "tc_total_dias": tc_atual.dias_total,
        "tc_total_texto": f"{tc_atual.anos}a {tc_atual.meses_restantes}m {tc_atual.dias_restantes}d",
        "tc_sem_b31_dias": tc_sem_b31.dias_total,
        "tc_sem_b31_texto": f"{tc_sem_b31.anos}a {tc_sem_b31.meses_restantes}m {tc_sem_b31.dias_restantes}d",
        "dias_b31_intercalado": dias_b31,
        "meses_b31_intercalado": round(dias_b31 / 30),
        "carencia_meses": carencia_meses,
        "carencia_exigida": carencia_exigida,
        "faltam_carencia": faltam_carencia,
        "faltam_carencia_texto": f"{faltam_carencia // 12}a {faltam_carencia % 12}m" if faltam_carencia > 0 else "Completa",
        "carencia_ok": carencia_meses >= carencia_exigida,
        "gargalo": "carencia" if faltam_carencia > 0 and tc_atual.anos >= 15 else
                   "tc" if tc_atual.anos < 15 else
                   "nenhum",
        "explicacao": (
            f"O segurado possui {tc_atual.anos}a {tc_atual.meses_restantes}m de TC total, "
            f"dos quais ~{round(dias_b31/30)} meses correspondem a auxilio-doenca intercalado (B31). "
            f"Esses periodos contam como TC (Art. 60 par. 3 Lei 8.213/91) mas NAO como carencia. "
            f"A carencia efetiva e de {carencia_meses} meses (de {carencia_exigida} exigidos). "
            f"Faltam {faltam_carencia} meses de contribuicao efetiva."
        ) if dias_b31 > 0 else "",
        "beneficios_b31": [
            {
                "dib": b.dib.strftime("%d/%m/%Y"),
                "dcb": b.dcb.strftime("%d/%m/%Y") if b.dcb else "ATIVO",
                "dias": (min(b.dcb or der_base, der_base) - b.dib).days if b.dib else 0,
            }
            for b in (segurado.beneficios_anteriores or [])
            if b.especie.value in ("B31", "B91") and b.dib and b.dcb
        ],
    }

    projecoes_list = list(projecoes.values())

    resumo = _gerar_resumo_executivo(segurado, projecoes_list, tc_atual, qualidade, der_base)

    # Novos diferenciais
    score = _calcular_score_prontidao(segurado, der_base, tc_atual, qualidade, projecoes)
    marcos = _tc_marcos_legais(segurado, der_base)
    comp_sem_sal = _competencias_sem_salarios(segurado)

    # Análise de atividade especial por vínculo
    analise_especial = _analisar_especial_vinculos(segurado)

    # Memória de cálculo
    memoria = _gerar_memoria(segurado, der_base)

    # Análise de revisão (placeholder — preenchido pelo router quando há benefício)
    # O router adiciona analise_revisao ao resultado quando benefícios são detectados

    resultado = {
        "der_base": der_base,
        "tc_atual": tc_info,
        "carencia_meses": carencia_meses,
        "analise_tc_carencia": analise_tc_carencia,
        "salario_projetado": sal,
        "elegiveis_agora": len(elegiveis_hoje) > 0,
        "melhor_data": melhor_data,
        "melhor_regra": melhor_regra_nome,
        "melhor_rmi": melhor_rmi,
        "projecoes": projecoes_list,
        "recomendacao": _recomendacao_geral(projecoes, elegiveis_hoje, segurado, der_base),
        "argumentos_cliente": _argumentos_cliente(projecoes, segurado, der_base, tc_atual),
        "custo_beneficio": _calcular_custo_beneficio(projecoes, segurado, der_base, sal),
        "expectativa_vida": _expectativa_vida(segurado),
        "qualidade_segurado": qualidade,
        "pensao_projetada": pensao,
        "cenarios_vida": cenarios,
        "plano_acao": plano,
        "resumo_executivo": resumo,
        "score_prontidao": score,
        "marcos_legais": marcos,
        "competencias_sem_salario": comp_sem_sal,
        "analise_especial": analise_especial,
        "memoria_calculo": memoria,
        "regime_aplicado": "PRE_REFORMA" if der_base < _DC.EC_103_2019 else "POS_REFORMA_EC103",
    }

    # VALIDACAO ANTIALUCINACAO — audita o resultado antes de devolver
    try:
        from ..validacao.antialucinacao import validar_resultado_planejamento
        resultado = validar_resultado_planejamento(resultado, der_base)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro na validacao antialucinacao: {e}")

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def _media_salario_atual(segurado: Segurado, der: date) -> Decimal:
    """Calcula a média dos últimos 12 salários de contribuição."""
    todas = []
    for v in segurado.vinculos:
        todas.extend(v.contribuicoes)
    if not todas:
        return salario_minimo_na_data(der)
    todas_ord = sorted(todas, key=lambda c: c.competencia, reverse=True)
    ultimas = todas_ord[:12]
    if not ultimas:
        return salario_minimo_na_data(der)
    soma = sum(c.salario_contribuicao for c in ultimas)
    return (soma / Decimal(str(len(ultimas)))).quantize(Decimal("0.01"))


def _adicionar_bloco_anual(segurado: Segurado, der_base: date, salario: Decimal, n_meses: int):
    """Adiciona um único vínculo futuro com n_meses competências mensais."""
    from ..enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado
    from ..models.vinculo import Vinculo

    contribuicoes = []
    d = _inicio_proximo_mes(der_base)
    for _ in range(n_meses):
        contribuicoes.append(Contribuicao(
            competencia=date(d.year, d.month, 1),
            salario_contribuicao=salario,
        ))
        d = _avancar_mes(d)

    v = Vinculo(
        tipo_vinculo=TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        empregador_nome="Projeção Futura",
        data_inicio=_inicio_proximo_mes(der_base),
        data_fim=None,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
    )
    segurado.vinculos.append(v)


def _avancar_meses(d: date, n: int) -> date:
    """Avança n meses a partir de d."""
    for _ in range(n):
        d = _avancar_mes(d)
    return d


def _garantir_vinculo_projecao(segurado: Segurado):
    """Garante que existe um vínculo de projeção aberto para acumular contribuições."""
    from ..enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado
    from ..models.vinculo import Vinculo
    # Se o último vínculo está fechado (data_fim definida), cria um novo aberto
    if not segurado.vinculos or segurado.vinculos[-1].data_fim is not None:
        v = Vinculo(
            tipo_vinculo=TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
            regime=RegimePrevidenciario.RGPS,
            tipo_atividade=TipoAtividade.NORMAL,
            empregador_nome="Projeção Futura",
            data_inicio=date.today(),
            data_fim=None,
            contribuicoes=[],
            origem=OrigemDado.MANUAL,
        )
        segurado.vinculos.append(v)


def _acumular_competencia(segurado: Segurado, data: date, salario: Decimal):
    """Adiciona competência diretamente ao vínculo de projeção (sem deepcopy)."""
    comp = date(data.year, data.month, 1)
    nova_contrib = Contribuicao(competencia=comp, salario_contribuicao=salario)
    # O último vínculo é sempre o de projeção (aberto)
    segurado.vinculos[-1].contribuicoes.append(nova_contrib)


def _criar_vinculo_projecao(segurado: Segurado, comp: date, salario: Decimal):
    from ..models.vinculo import Vinculo
    from ..enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado
    v = Vinculo(
        tipo_vinculo=TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        empregador_nome="Projeção Futura",
        data_inicio=comp,
        data_fim=None,
        contribuicoes=[Contribuicao(competencia=comp, salario_contribuicao=salario)],
        origem=OrigemDado.MANUAL,
    )
    segurado.vinculos.append(v)


def _inicio_proximo_mes(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _avancar_mes(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _formatar_periodo(anos: int, meses: int) -> str:
    partes = []
    if anos:
        partes.append(f"{anos} {'ano' if anos == 1 else 'anos'}")
    if meses:
        partes.append(f"{meses} {'mês' if meses == 1 else 'meses'}")
    if not partes:
        return "menos de 1 mês"
    return " e ".join(partes)


def _mensagem_cliente(regra: str, anos: int, meses: int, data: date, rmi: Decimal) -> str:
    periodo = _formatar_periodo(anos, meses)
    data_str = data.strftime("%d/%m/%Y")
    rmi_str = f"R$ {rmi:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    if anos == 0 and meses == 0:
        return f"Você já pode se aposentar hoje por esta regra, com RMI de {rmi_str}."

    if "Pontos" in regra:
        return (
            f"Pela regra de pontos, você poderá se aposentar em {data_str} "
            f"(faltam {periodo}), com renda mensal de {rmi_str}. "
            f"Esta regra exige soma de idade + tempo de contribuição."
        )
    elif "Idade" in regra and "Progressiva" in regra:
        return (
            f"Pela regra de idade progressiva, sua aposentadoria será em {data_str} "
            f"(faltam {periodo}), com renda de {rmi_str}. "
            f"Exige tempo de contribuição completo (35H/30M) e idade mínima crescente."
        )
    elif "Pedágio 50" in regra:
        return (
            f"Pela regra do pedágio 50%, você se aposenta em {data_str} "
            f"(faltam {periodo}), com renda de {rmi_str}. "
            f"Esta é uma das regras mais favoráveis para quem estava próximo de se aposentar em 2019."
        )
    elif "Pedágio 100" in regra:
        return (
            f"Pela regra do pedágio 100%, você se aposenta em {data_str} "
            f"(faltam {periodo}), com renda de {rmi_str}. "
            f"Exige dobrar o tempo que faltava em novembro de 2019."
        )
    elif "Idade" in regra:
        return (
            f"Pela aposentadoria por idade, você terá direito em {data_str} "
            f"(faltam {periodo}), com renda de {rmi_str}. "
            f"Exige 65 anos (homem) ou 62 anos (mulher) e 180 meses de contribuição."
        )
    else:
        return f"Aposentadoria prevista para {data_str} (faltam {periodo}), com renda de {rmi_str}."


def _recomendacao_geral(
    projecoes: Dict, elegiveis_hoje: list, segurado: Segurado, der: date
) -> str:
    if elegiveis_hoje:
        melhor = max(elegiveis_hoje, key=lambda c: c.rmi_teto)
        rmi = f"R$ {melhor.rmi_teto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return (
            f"✅ ATENÇÃO: {segurado.dados_pessoais.nome.split()[0]} já tem direito à aposentadoria HOJE "
            f"pela regra '{melhor.nome_regra}', com RMI de {rmi}. "
            f"Recomenda-se dar entrada no requerimento imediatamente para não perder competências."
        )

    # Encontra a data mais próxima entre regras alcançáveis
    alcancaveis = [p for p in projecoes.values() if p.get("data_elegibilidade")]
    if not alcancaveis:
        return "Nenhuma regra de aposentadoria projetável nos próximos 40 anos com o perfil atual."

    melhor = min(alcancaveis, key=lambda p: p["meses_faltantes"])
    periodo = melhor["texto_faltante"]
    data_str = melhor["data_elegibilidade"].strftime("%d/%m/%Y")
    rmi = melhor["rmi_formatada"]

    # Verifica se há regra com RMI maior (mas mais tarde)
    maior_rmi = max(alcancaveis, key=lambda p: p["rmi_projetada"])
    if maior_rmi["regra"] != melhor["regra"] and maior_rmi["rmi_projetada"] > melhor["rmi_projetada"] * Decimal("1.05"):
        rmi_maior = maior_rmi["rmi_formatada"]
        meses_extra = maior_rmi["meses_faltantes"] - melhor["meses_faltantes"]
        return (
            f"📌 A aposentadoria mais próxima é pela regra '{melhor['regra']}' "
            f"em {data_str} (faltam {periodo}), com renda {rmi}. "
            f"Porém, aguardando mais {meses_extra} meses pela regra '{maior_rmi['regra']}', "
            f"a renda sobe para {rmi_maior}. "
            f"Analise se vale a pena esperar."
        )

    return (
        f"📌 A melhor estratégia é buscar aposentadoria pela regra '{melhor['regra']}' "
        f"a partir de {data_str} (faltam {periodo}), com renda estimada de {rmi}. "
        f"Mantenha as contribuições em dia para não perder esse prazo."
    )


def _argumentos_cliente(projecoes: Dict, segurado: Segurado, der: date, tc_atual) -> List[str]:
    """Gera lista de argumentos explicativos para apresentar ao cliente."""
    args = []
    nome = segurado.dados_pessoais.nome.split()[0]

    args.append(
        f"Seu histórico no CNIS registra {tc_atual.anos} anos, {tc_atual.meses_restantes} meses "
        f"e {tc_atual.dias_restantes} dias de tempo de contribuição ao RGPS."
    )

    alcancaveis = sorted(
        [p for p in projecoes.values() if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"]
    )

    if alcancaveis:
        mais_rapida = alcancaveis[0]
        args.append(
            f"A aposentadoria mais rápida disponível é pela regra '{mais_rapida['regra']}', "
            f"prevista para {mais_rapida['data_elegibilidade'].strftime('%d/%m/%Y')} "
            f"(faltam {mais_rapida['texto_faltante']}), "
            f"com renda mensal estimada de {mais_rapida['rmi_formatada']}."
        )

    if len(alcancaveis) >= 2:
        segunda = alcancaveis[1]
        args.append(
            f"Uma alternativa é aguardar a regra '{segunda['regra']}' "
            f"com data prevista em {segunda['data_elegibilidade'].strftime('%d/%m/%Y')}, "
            f"que oferece renda de {segunda['rmi_formatada']}."
        )

    args.append(
        "Importante: as datas projetadas assumem contribuição contínua. "
        "Períodos sem contribuição (desemprego, doença) atrasam a elegibilidade."
    )

    args.append(
        "O valor da renda (RMI) é uma estimativa baseada nos salários atuais. "
        "Aumentos salariais futuros e correção monetária podem alterar este valor."
    )

    teto = teto_na_data(der)
    args.append(
        f"O teto do INSS em {der.strftime('%m/%Y')} é de "
        f"R$ {teto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") +
        ". Salários acima deste valor não aumentam a aposentadoria."
    )

    args.append(
        "Verifique se há mais de um NIT/PIS/PASEP vinculado ao CPF. É comum que trabalhadores "
        "que alternaram entre emprego formal, autônomo ou MEI tenham cadastros fragmentados no INSS, "
        "com contribuições 'perdidas' em outro NIT. A unificação pode ser solicitada pelo 135 ou Meu INSS "
        "e pode revelar tempo de contribuição adicional decisivo para a aposentadoria."
    )

    return args


# ─────────────────────────────────────────────────────────────────────────────
# Expectativa de vida e custo-benefício
# ─────────────────────────────────────────────────────────────────────────────

# Fonte: IBGE — Tábuas Completas de Mortalidade 2024 (publicado nov/2025)
_EXPECTATIVA_VIDA = {
    "MASCULINO": Decimal("73.3"),
    "FEMININO":  Decimal("79.9"),
}
_EXPECTATIVA_MEDIA = Decimal("76.6")

# Alíquotas de contribuição por modalidade
_ALIQUOTAS = {
    "empregado":    Decimal("0.11"),  # até teto (~11% médio)
    "autonomo_ci":  Decimal("0.20"),  # contribuinte individual
    "facultativo":  Decimal("0.20"),  # segurado facultativo
    "mei_5pct":     Decimal("0.05"),  # MEI — NÃO conta para TC
}


def _expectativa_vida(segurado: Segurado) -> Dict[str, Any]:
    sexo = str(segurado.sexo).upper()
    ev = _EXPECTATIVA_VIDA.get(sexo, _EXPECTATIVA_MEDIA)
    return {
        "anos": float(ev),
        "sexo": sexo,
        "fonte": "IBGE — Tábuas Completas de Mortalidade 2024",
    }


def _calcular_custo_beneficio(
    projecoes: Dict,
    segurado: Segurado,
    der_base: date,
    salario: Decimal,
) -> List[Dict]:
    """
    Para cada projeção alcançável, calcula o custo-benefício de contribuir
    até a data de elegibilidade nas modalidades: empregado, autônomo/CI e facultativo.

    Retorna lista de dicts com análise completa por regra.
    """
    sexo = str(segurado.sexo).upper()
    ev_anos = _EXPECTATIVA_VIDA.get(sexo, _EXPECTATIVA_MEDIA)
    dn = segurado.dados_pessoais.data_nascimento
    idade_atual = Decimal(str((der_base - dn).days / 365.25))

    resultado = []

    alcancaveis = sorted(
        [p for p in projecoes.values() if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"]
    )

    for p in alcancaveis:
        meses_faltantes = Decimal(str(p["meses_faltantes"]))
        rmi = p["rmi_projetada"]
        if not rmi or rmi <= 0:
            continue

        idade_aposentadoria = idade_atual + meses_faltantes / 12
        meses_recebendo = max(Decimal("0"), (ev_anos - idade_aposentadoria) * 12)

        total_recebido = rmi * meses_recebendo

        modalidades = []
        for nome_mod, aliquota in [
            ("Empregado (CLT)", _ALIQUOTAS["empregado"]),
            ("Autônomo / Contribuinte Individual", _ALIQUOTAS["autonomo_ci"]),
            ("Segurado Facultativo", _ALIQUOTAS["facultativo"]),
        ]:
            contrib_mensal = (salario * aliquota).quantize(Decimal("0.01"))
            total_pago = (contrib_mensal * meses_faltantes).quantize(Decimal("0.01"))

            if total_pago > 0 and rmi > 0:
                meses_retorno = (total_pago / rmi).quantize(Decimal("0.1"))
                anos_retorno = (meses_retorno / 12).quantize(Decimal("0.1"))
            else:
                meses_retorno = Decimal("0")
                anos_retorno = Decimal("0")

            lucro_liquido = (total_recebido - total_pago).quantize(Decimal("0.01"))
            roi_pct = (
                ((total_recebido - total_pago) / total_pago * 100).quantize(Decimal("0.1"))
                if total_pago > 0 else Decimal("0")
            )

            modalidades.append({
                "modalidade": nome_mod,
                "aliquota_pct": float(aliquota * 100),
                "contribuicao_mensal": str(contrib_mensal),
                "total_pago_ate_apos": str(total_pago),
                "meses_para_recuperar": str(meses_retorno),
                "anos_para_recuperar": str(anos_retorno),
                "total_recebido_ate_obito": str(total_recebido.quantize(Decimal("0.01"))),
                "lucro_liquido": str(lucro_liquido),
                "roi_percentual": str(roi_pct),
                "vale_a_pena": lucro_liquido > 0,
            })

        resultado.append({
            "regra": p["regra"],
            "data_elegibilidade": p["data_elegibilidade"].strftime("%d/%m/%Y") if p.get("data_elegibilidade") else "—",
            "meses_faltantes": int(meses_faltantes),
            "rmi": str(rmi),
            "rmi_formatada": p["rmi_formatada"],
            "idade_aposentadoria": float(idade_aposentadoria.quantize(Decimal("0.1"))),
            "meses_recebendo": float(meses_recebendo.quantize(Decimal("0.1"))),
            "total_recebido": str(total_recebido.quantize(Decimal("0.01"))),
            "expectativa_vida_anos": float(ev_anos),
            "modalidades": modalidades,
            "disclaimer": (
                "AVISO: Esta analise de custo-beneficio e uma projecao NOMINAL simplificada. "
                "NAO constitui analise atuarial. Nao considera inflacao, reajustes reais, "
                "tributacao, valor presente do dinheiro no tempo nem risco de mortalidade. "
                "Serve APENAS como referencia ilustrativa para decisao do segurado sobre "
                "manter contribuicoes. NAO deve ser apresentada como garantia de retorno."
            ),
            "tipo_dado": "PROJECAO_SIMPLIFICADA",
        })

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Qualidade de Segurado
# ─────────────────────────────────────────────────────────────────────────────

def _analisar_qualidade_segurado(segurado: Segurado, der_base: date) -> Dict[str, Any]:
    """
    Analisa a qualidade de segurado na data de referencia.

    Regras de periodo de graca (Art. 15, Lei 8.213/91):
      - 12 meses para empregado/CI
      - +12 meses se possui 120+ contribuicoes sem perda de qualidade
      - 3 meses para facultativo

    IMPORTANTE: Se o segurado possui beneficio ATIVO (aposentadoria em manutencao),
    a qualidade de segurado e MANTIDA independentemente de contribuicoes recentes
    (Art. 15, caput, Lei 8.213/91).
    """
    # VERIFICAR BENEFICIO ATIVO PRIMEIRO
    # Se o segurado tem aposentadoria/beneficio em manutencao, qualidade mantida
    beneficio_ativo = False
    if segurado.beneficios_anteriores:
        for b in segurado.beneficios_anteriores:
            # Beneficio ativo = tem DIB mas NAO tem DCB (nao cessou)
            if b.dib and not b.dcb:
                beneficio_ativo = True
                break

    if beneficio_ativo:
        return {
            "ultima_contribuicao": "Beneficio ativo",
            "periodo_graca_meses": 0,
            "data_perda_qualidade": None,
            "status": "ATIVA",
            "dias_restantes": 9999,
            "mensagem": (
                "Qualidade de segurado MANTIDA — o segurado possui beneficio ativo em manutencao. "
                "Enquanto o beneficio estiver ativo, a qualidade de segurado e preservada "
                "(Art. 15, caput, Lei 8.213/91)."
            ),
            "fonte": "BENEFICIO_ATIVO",
            "nivel_confianca": "DADO_PRIMARIO",
        }

    # Encontrar ultima contribuicao entre todos os vinculos
    todas_contribs: List[Contribuicao] = []
    for v in segurado.vinculos:
        todas_contribs.extend(v.contribuicoes)

    if not todas_contribs:
        return {
            "ultima_contribuicao": None,
            "periodo_graca_meses": 0,
            "data_perda_qualidade": None,
            "status": "PERDIDA",
            "dias_restantes": 0,
            "mensagem": "Nenhuma contribuicao encontrada no historico. A qualidade de segurado nao pode ser verificada.",
            "fonte": "SEM_DADOS",
            "nivel_confianca": "INSUFICIENTE",
        }

    todas_contribs.sort(key=lambda c: c.competencia)
    ultima = todas_contribs[-1]
    total_contribs = len(todas_contribs)

    # Determinar tipo de vinculo da ultima contribuicao para definir graca
    ultimo_vinculo = None
    for v in segurado.vinculos:
        if any(c.competencia == ultima.competencia for c in v.contribuicoes):
            ultimo_vinculo = v
            break

    tipo_str = str(getattr(ultimo_vinculo, "tipo_vinculo", "")).upper() if ultimo_vinculo else ""

    # Periodo de graca base
    if "FACULTATIVO" in tipo_str:
        periodo_graca = 3
    else:
        periodo_graca = 12

    # +12 meses se 120+ contribuicoes sem perda de qualidade
    if total_contribs >= 120:
        periodo_graca += 12

    # Data de perda de qualidade = mes seguinte ao fim do periodo de graca
    data_perda = _avancar_meses(date(ultima.competencia.year, ultima.competencia.month, 1), periodo_graca + 1)

    # Dias restantes
    delta = (data_perda - der_base).days

    if delta < 0:
        status = "PERDIDA"
        dias_restantes = 0
        mensagem = (
            f"A qualidade de segurado foi perdida em {data_perda.strftime('%d/%m/%Y')}. "
            f"Ultima contribuicao: {ultima.competencia.strftime('%m/%Y')}. "
            f"E necessario realizar novas contribuicoes para recuperar a condicao de segurado."
        )
    elif delta <= 90:
        status = "EM_RISCO"
        dias_restantes = delta
        mensagem = (
            f"ATENCAO: A qualidade de segurado expira em {data_perda.strftime('%d/%m/%Y')} "
            f"(restam {dias_restantes} dias). Contribua imediatamente para nao perder a condicao de segurado."
        )
    else:
        status = "ATIVA"
        dias_restantes = delta
        mensagem = (
            f"Qualidade de segurado ativa. Periodo de graca ate {data_perda.strftime('%d/%m/%Y')} "
            f"(restam {dias_restantes} dias). Ultima contribuicao: {ultima.competencia.strftime('%m/%Y')}."
        )

    return {
        "ultima_contribuicao": ultima.competencia.strftime("%m/%Y"),
        "periodo_graca_meses": periodo_graca,
        "data_perda_qualidade": data_perda.strftime("%d/%m/%Y"),
        "status": status,
        "dias_restantes": dias_restantes,
        "mensagem": mensagem,
        "fonte": "CONTRIBUICOES_CNIS",
        "nivel_confianca": "DADO_PRIMARIO",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pensão por Morte (EC 103/2019)
# ─────────────────────────────────────────────────────────────────────────────

def _projetar_pensao(segurado: Segurado, der_base: date, rmi_melhor: Decimal) -> Dict[str, Any]:
    """
    Projeta o valor da pensão por morte conforme EC 103/2019.

    Regra: 50% + 10% por dependente habilitado (máximo 100%).
    Como não temos dados de dependentes, projeta cenários com 1 e 2 dependentes.
    """
    if not rmi_melhor or rmi_melhor <= 0:
        # Usa salário mínimo como referência mínima
        rmi_base = salario_minimo_na_data(der_base)
    else:
        rmi_base = rmi_melhor

    cenarios = []
    for n_dep in (1, 2, 3):
        cota_pct = min(50 + (10 * n_dep), 100)
        valor = (rmi_base * Decimal(str(cota_pct)) / Decimal("100")).quantize(Decimal("0.01"))
        # Piso: salário mínimo
        piso = salario_minimo_na_data(der_base)
        if valor < piso:
            valor = piso
        valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        cenarios.append({
            "dependentes": n_dep,
            "cota_pct": cota_pct,
            "valor": valor,
            "valor_formatado": valor_fmt,
        })

    rmi_fmt = f"R$ {rmi_base:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return {
        "rmi_base": rmi_base,
        "rmi_base_formatada": rmi_fmt,
        "cenarios": cenarios,
        "mensagem": (
            f"Se o segurado falecer hoje, a pensão por morte será calculada sobre a RMI de {rmi_fmt}. "
            f"Regra EC 103/2019: 50% + 10% por dependente habilitado. "
            f"Com 1 dependente: {cenarios[0]['valor_formatado']}; "
            f"com 2 dependentes: {cenarios[1]['valor_formatado']}."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cenários de Vida Quantificados
# ─────────────────────────────────────────────────────────────────────────────

# Salário mínimo 2025 para cálculos de MEI
_SALARIO_MINIMO_2025 = Decimal("1518.00")


def _cenarios_vida_quantificados(
    segurado: Segurado,
    der_base: date,
    projecoes: Dict[str, Dict],
    salario: Decimal,
) -> List[Dict[str, Any]]:
    """
    Calcula cenários de contribuição com custos reais e impacto.

    Cenários:
      A) CLT (empregado) — inclui FGTS de 8% do empregador
      B) MEI 5% — sobre salário mínimo, NÃO conta para TC
      C) Facultativo 20% — sobre salário declarado
      D) Complementação MEI 15% — adicional sobre salário mínimo
      E) Autônomo/CI 20% — sobre salário como contribuinte individual
    """
    # Encontra a melhor projeção alcançável (mais cedo)
    alcancaveis = sorted(
        [p for p in projecoes.values() if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"],
    )
    melhor = alcancaveis[0] if alcancaveis else None
    meses_ate_apos = melhor["meses_faltantes"] if melhor else 0
    rmi_melhor = melhor["rmi_projetada"] if melhor else Decimal("0")
    data_melhor = melhor["data_elegibilidade"] if melhor else None
    data_str = data_melhor.strftime("%d/%m/%Y") if data_melhor else "—"

    cenarios: List[Dict[str, Any]] = []

    # Cenário A: CLT
    aliq_clt = Decimal("0.11")
    custo_mensal_clt = (salario * aliq_clt).quantize(Decimal("0.01"))
    fgts_mensal = (salario * Decimal("0.08")).quantize(Decimal("0.01"))
    custo_anual_clt = (custo_mensal_clt * 12).quantize(Decimal("0.01"))
    total_clt = (custo_mensal_clt * meses_ate_apos).quantize(Decimal("0.01"))
    cenarios.append({
        "cenario": "A",
        "nome": "CLT (Empregado)",
        "descricao": "Contribuição como empregado CLT. Empregador deposita FGTS de 8% adicional.",
        "monthly_cost": custo_mensal_clt,
        "fgts_mensal": fgts_mensal,
        "annual_cost": custo_anual_clt,
        "total_cost_until_retirement": total_clt,
        "impact_on_date": data_str,
        "impact_on_rmi": rmi_melhor,
        "conta_para_tc": True,
        "observacao": f"Desconto em folha ~11%. Adicionalmente, o empregador deposita R$ {fgts_mensal} de FGTS/mês.",
    })

    # Cenário B: MEI 5%
    custo_mei = (_SALARIO_MINIMO_2025 * Decimal("0.05")).quantize(Decimal("0.01"))
    custo_anual_mei = (custo_mei * 12).quantize(Decimal("0.01"))
    total_mei = (custo_mei * meses_ate_apos).quantize(Decimal("0.01"))
    cenarios.append({
        "cenario": "B",
        "nome": "MEI (5% do salário mínimo)",
        "descricao": "Contribuição como MEI. ATENÇÃO: NÃO conta tempo para aposentadoria por tempo de contribuição.",
        "monthly_cost": custo_mei,
        "fgts_mensal": Decimal("0"),
        "annual_cost": custo_anual_mei,
        "total_cost_until_retirement": total_mei,
        "impact_on_date": "Não se aplica (só vale para aposentadoria por idade)",
        "impact_on_rmi": salario_minimo_na_data(der_base),
        "conta_para_tc": False,
        "observacao": "Custo mais baixo, porém limita a aposentadoria por idade e valor ao salário mínimo.",
    })

    # Cenário C: Facultativo 20%
    custo_fac = (salario * Decimal("0.20")).quantize(Decimal("0.01"))
    custo_anual_fac = (custo_fac * 12).quantize(Decimal("0.01"))
    total_fac = (custo_fac * meses_ate_apos).quantize(Decimal("0.01"))
    cenarios.append({
        "cenario": "C",
        "nome": "Segurado Facultativo (20%)",
        "descricao": "Contribuição como facultativo sobre o salário declarado. Conta para todas as regras.",
        "monthly_cost": custo_fac,
        "fgts_mensal": Decimal("0"),
        "annual_cost": custo_anual_fac,
        "total_cost_until_retirement": total_fac,
        "impact_on_date": data_str,
        "impact_on_rmi": rmi_melhor,
        "conta_para_tc": True,
        "observacao": "Ideal para quem não tem vínculo empregatício. Mesmo progression de TC que CLT.",
    })

    # Cenário D: Complementação MEI 15%
    custo_compl = (_SALARIO_MINIMO_2025 * Decimal("0.15")).quantize(Decimal("0.01"))
    custo_anual_compl = (custo_compl * 12).quantize(Decimal("0.01"))
    total_compl = (custo_compl * meses_ate_apos).quantize(Decimal("0.01"))
    custo_total_mei_compl = custo_mei + custo_compl
    cenarios.append({
        "cenario": "D",
        "nome": "Complementação MEI (+15% do salário mínimo)",
        "descricao": "Paga 15% adicional sobre o salário mínimo para que o tempo como MEI conte para TC.",
        "monthly_cost": custo_compl,
        "custo_total_com_mei": custo_total_mei_compl,
        "fgts_mensal": Decimal("0"),
        "annual_cost": custo_anual_compl,
        "total_cost_until_retirement": total_compl,
        "impact_on_date": data_str,
        "impact_on_rmi": salario_minimo_na_data(der_base),
        "conta_para_tc": True,
        "observacao": f"Custo total MEI + complementação: R$ {custo_total_mei_compl}/mês. RMI limitada ao salário mínimo.",
    })

    # Cenário E: Autônomo / CI 20%
    custo_ci = (salario * Decimal("0.20")).quantize(Decimal("0.01"))
    custo_anual_ci = (custo_ci * 12).quantize(Decimal("0.01"))
    total_ci = (custo_ci * meses_ate_apos).quantize(Decimal("0.01"))
    cenarios.append({
        "cenario": "E",
        "nome": "Autônomo / Contribuinte Individual (20%)",
        "descricao": "Contribuição como autônomo (CI) sobre o salário de contribuição. Conta para todas as regras.",
        "monthly_cost": custo_ci,
        "fgts_mensal": Decimal("0"),
        "annual_cost": custo_anual_ci,
        "total_cost_until_retirement": total_ci,
        "impact_on_date": data_str,
        "impact_on_rmi": rmi_melhor,
        "conta_para_tc": True,
        "observacao": "Mesma progressão que facultativo. Exige comprovação de atividade remunerada.",
    })

    return cenarios


# ─────────────────────────────────────────────────────────────────────────────
# Plano de Ação
# ─────────────────────────────────────────────────────────────────────────────

def _gerar_plano_acao(
    segurado: Segurado,
    der_base: date,
    projecoes: Dict[str, Dict],
    qualidade_segurado: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Gera um plano de ação numerado com passos concretos para o segurado.
    """
    passos: List[Dict[str, Any]] = []

    # Passo 1: Verificar e corrigir CNIS
    tem_vinculos = len(segurado.vinculos) > 0
    nit = segurado.dados_pessoais.nit or ""
    if tem_vinculos:
        desc_cnis = (
            f"Solicitar extrato CNIS atualizado no Meu INSS e conferir todos os {len(segurado.vinculos)} vínculos. "
            "Verificar se há períodos faltantes, salários incorretos ou vínculos não registrados. "
            "Se houver divergências, juntar carteira de trabalho, holerites e PPP para retificação. "
            "IMPORTANTE: Verificar se o segurado possui mais de um NIT/PIS/PASEP — cadastro fragmentado "
            "pode esconder tempo de contribuição. Ligar no 135 para consultar todos os NITs vinculados ao CPF."
        )
    else:
        desc_cnis = (
            "Nenhum vínculo encontrado. Verificar se há contribuições não registradas no CNIS. "
            "Buscar carteira de trabalho, carnês de contribuição e documentos antigos. "
            "Verificar se existem outros números NIT/PIS vinculados ao CPF — contribuições podem estar em cadastro separado."
        )
    passos.append({
        "numero": 1,
        "titulo": "Verificar e corrigir o CNIS",
        "descricao": desc_cnis,
        "prazo": "Imediato — até 30 dias",
        "urgencia": "ALTA",
    })

    # Passo 2: Qualidade de segurado
    status_qs = qualidade_segurado.get("status", "PERDIDA")
    if status_qs == "ATIVA":
        desc_qs = (
            f"Qualidade de segurado ATIVA (expira em {qualidade_segurado.get('data_perda_qualidade', date.today().strftime('%d/%m/%Y'))}). "
            "Manter contribuições regulares para não perder a condição."
        )
        urgencia_qs = "BAIXA"
        prazo_qs = "Mensal — manter contribuições"
    elif status_qs == "EM_RISCO":
        desc_qs = (
            f"ATENÇÃO: Qualidade de segurado expira em {qualidade_segurado.get('dias_restantes', 0)} dias. "
            "Realizar contribuição IMEDIATAMENTE para evitar perda de qualidade e dos benefícios."
        )
        urgencia_qs = "ALTA"
        prazo_qs = "URGENTE — contribuir este mês"
    else:
        desc_qs = (
            "Qualidade de segurado PERDIDA. É necessário realizar novas contribuições para recuperar "
            "a condição de segurado. Após a primeira contribuição, a qualidade é restabelecida."
        )
        urgencia_qs = "ALTA"
        prazo_qs = "URGENTE — contribuir imediatamente"
    passos.append({
        "numero": 2,
        "titulo": "Situação da qualidade de segurado",
        "descricao": desc_qs,
        "prazo": prazo_qs,
        "urgencia": urgencia_qs,
    })

    # Passo 3: Melhor estratégia de contribuição
    alcancaveis = sorted(
        [p for p in projecoes.values() if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"],
    )
    if alcancaveis:
        melhor = alcancaveis[0]
        meses = melhor["meses_faltantes"]
        rmi_fmt = melhor.get("rmi_formatada", "—")
        desc_contrib = (
            f"A regra mais próxima é '{melhor['regra']}', faltando {melhor.get('texto_faltante', f'{meses} meses')}. "
            f"RMI estimada: {rmi_fmt}. "
            "Recomendação: contribuir como empregado CLT ou contribuinte individual (20%) para manter "
            "a progressão do tempo de contribuição. Evitar MEI 5% se busca aposentadoria por tempo."
        )
    else:
        desc_contrib = (
            "Nenhuma regra alcançável nos próximos 40 anos com o perfil atual. "
            "Consulte um advogado previdenciarista para avaliar alternativas."
        )
    passos.append({
        "numero": 3,
        "titulo": "Estratégia de contribuição recomendada",
        "descricao": desc_contrib,
        "prazo": "Definir nos próximos 30 dias",
        "urgencia": "MEDIA",
    })

    # Passo 4: Quando dar entrada no benefício
    if alcancaveis:
        data_elig = alcancaveis[0]["data_elegibilidade"]
        data_requerimento = data_elig.strftime("%d/%m/%Y")
        # Sugerir dar entrada 90 dias antes para agilizar
        from datetime import timedelta
        data_inicio_proc = data_elig - timedelta(days=90)
        desc_entrada = (
            f"Data prevista de elegibilidade: {data_requerimento}. "
            f"Iniciar preparação do requerimento a partir de {data_inicio_proc.strftime('%d/%m/%Y')} (90 dias antes). "
            "Agendar atendimento no Meu INSS ou INSS Digital para protocolar o pedido."
        )
        prazo_entrada = f"A partir de {data_inicio_proc.strftime('%d/%m/%Y')}"
        urgencia_entrada = "MEDIA"
    else:
        desc_entrada = "Sem data de elegibilidade projetada. Reavaliar após regularizar contribuições."
        prazo_entrada = "Indefinido"
        urgencia_entrada = "BAIXA"
    passos.append({
        "numero": 4,
        "titulo": "Quando requerer o benefício",
        "descricao": desc_entrada,
        "prazo": prazo_entrada,
        "urgencia": urgencia_entrada,
    })

    # Passo 5: Documentos a preparar
    passos.append({
        "numero": 5,
        "titulo": "Documentos a preparar",
        "descricao": (
            "Reunir os seguintes documentos: "
            "(1) RG e CPF; "
            "(2) Carteira de Trabalho (física e/ou digital); "
            "(3) Extrato CNIS atualizado; "
            "(4) Carnês de contribuição (GPS) se houver períodos como autônomo; "
            "(5) PPP — Perfil Profissiográfico Previdenciário (se trabalhou em atividade especial); "
            "(6) Comprovante de residência atualizado; "
            "(7) Dados bancários para recebimento do benefício."
        ),
        "prazo": "Reunir com antecedência de 90 dias da data de requerimento",
        "urgencia": "MEDIA",
    })

    return passos


# ─────────────────────────────────────────────────────────────────────────────
# Resumo Executivo
# ─────────────────────────────────────────────────────────────────────────────

def _gerar_resumo_executivo(
    segurado: Segurado,
    projecoes: List[Dict],
    tc_atual,
    qualidade: Dict[str, Any],
    der_base: date,
) -> Dict[str, str]:
    """
    Gera um resumo executivo em português claro, voltado ao cliente.
    """
    nome = segurado.dados_pessoais.nome.split()[0]
    dn = segurado.dados_pessoais.data_nascimento
    idade_anos = (der_base - dn).days // 365

    # Situação atual
    tc_texto = f"{tc_atual.anos} anos, {tc_atual.meses_restantes} meses e {tc_atual.dias_restantes} dias"
    status_qs = qualidade.get("status", "PERDIDA")
    if status_qs == "ATIVA":
        qs_texto = "ativa"
    elif status_qs == "EM_RISCO":
        qs_texto = "em risco de perda"
    else:
        qs_texto = "perdida"

    situacao_atual = (
        f"{nome}, {idade_anos} anos, possui {tc_texto} de tempo de contribuição. "
        f"Qualidade de segurado: {qs_texto}."
    )

    # Melhor caminho
    alcancaveis = sorted(
        [p for p in projecoes if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"],
    )

    if alcancaveis:
        melhor = alcancaveis[0]
        data_str = melhor["data_elegibilidade"].strftime("%d/%m/%Y")
        rmi_fmt = melhor.get("rmi_formatada", "—")
        texto_faltante = melhor.get("texto_faltante", "—")
        melhor_caminho = (
            f"A aposentadoria mais próxima é pela regra '{melhor['regra']}', "
            f"prevista para {data_str} (faltam {texto_faltante}), "
            f"com renda mensal estimada de {rmi_fmt}."
        )
    else:
        melhor_caminho = (
            "No momento, não há regra de aposentadoria alcançável nos próximos 40 anos. "
            "Recomenda-se consultar um advogado previdenciarista."
        )

    # Ação imediata
    if status_qs == "PERDIDA":
        acao_imediata = "Realizar contribuição imediatamente para recuperar a qualidade de segurado."
    elif status_qs == "EM_RISCO":
        acao_imediata = (
            f"Contribuir neste mês para evitar a perda de qualidade de segurado "
            f"(restam {qualidade.get('dias_restantes', 0)} dias)."
        )
    else:
        acao_imediata = "Solicitar extrato CNIS atualizado e conferir todos os vínculos e salários registrados."

    # Próximo passo
    if alcancaveis:
        proximo_passo = (
            "Manter contribuições regulares e acompanhar o CNIS para garantir que todos os períodos "
            "estejam corretamente registrados. Iniciar preparação dos documentos com 90 dias de antecedência."
        )
    else:
        proximo_passo = (
            "Verificar se existem períodos de trabalho não registrados no CNIS que possam ser averbados."
        )

    return {
        "situacao_atual": situacao_atual,
        "melhor_caminho": melhor_caminho,
        "acao_imediata": acao_imediata,
        "proximo_passo": proximo_passo,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Score de Prontidão Previdenciária (0–1000) — EXCLUSIVO SistPrev
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_score_prontidao(
    segurado: Segurado,
    der_base: date,
    tc_atual,
    qualidade: Dict[str, Any],
    projecoes: Dict[str, Dict],
) -> Dict[str, Any]:
    """
    Calcula um score de 0 a 1000 que mede o quão pronto o segurado está
    para se aposentar. Nenhum software concorrente oferece isso.

    Componentes do score (peso):
      1. Tempo de Contribuição (300 pts) — % do tempo necessário atingido
      2. Idade (200 pts) — % da idade mínima atingida
      3. Carência (150 pts) — % das 180 contribuições mínimas
      4. Qualidade de Segurado (100 pts) — ativa=100, risco=50, perdida=0
      5. Proximidade da Aposentadoria (150 pts) — quão perto está da data
      6. Valor do Benefício (100 pts) — RMI projetada vs teto do INSS
    """
    dn = segurado.dados_pessoais.data_nascimento
    sexo = str(segurado.sexo).upper()
    idade_dias = (der_base - dn).days
    idade_anos = Decimal(str(idade_dias)) / Decimal("365.25")

    # ── 1. Tempo de Contribuição (0-300) ──
    tc_dias = tc_atual.dias_total
    # Tempo necessário: 35 anos (H) ou 30 anos (M) = regra geral
    tc_necessario_anos = 35 if "MASC" in sexo else 30
    tc_necessario_dias = tc_necessario_anos * 365
    pct_tc = min(Decimal(str(tc_dias)) / Decimal(str(tc_necessario_dias)), Decimal("1"))
    score_tc = int(pct_tc * 300)

    # ── 2. Idade (0-200) ──
    # Idade mínima: 65 (H) ou 62 (M)
    idade_min = Decimal("65") if "MASC" in sexo else Decimal("62")
    pct_idade = min(idade_anos / idade_min, Decimal("1"))
    score_idade = int(pct_idade * 200)

    # ── 3. Carência (0-150) ──
    todas_contribs = []
    for v in segurado.vinculos:
        todas_contribs.extend(v.competencias_carencia())
    total_carencia = len(todas_contribs)
    pct_carencia = min(Decimal(str(total_carencia)) / Decimal("180"), Decimal("1"))
    score_carencia = int(pct_carencia * 150)

    # ── 4. Qualidade de Segurado (0-100) ──
    status_qs = qualidade.get("status", "PERDIDA")
    if status_qs == "ATIVA":
        score_qs = 100
    elif status_qs == "EM_RISCO":
        score_qs = 50
    else:
        score_qs = 0

    # ── 5. Proximidade da Aposentadoria (0-150) ──
    alcancaveis = sorted(
        [p for p in projecoes.values() if p.get("data_elegibilidade")],
        key=lambda p: p["meses_faltantes"],
    )
    if alcancaveis:
        meses_faltantes = alcancaveis[0]["meses_faltantes"]
        if meses_faltantes == 0:
            score_prox = 150
        elif meses_faltantes <= 6:
            score_prox = 140
        elif meses_faltantes <= 12:
            score_prox = 120
        elif meses_faltantes <= 24:
            score_prox = 100
        elif meses_faltantes <= 60:
            score_prox = 70
        elif meses_faltantes <= 120:
            score_prox = 40
        else:
            score_prox = 10
    else:
        score_prox = 0

    # ── 6. Valor do Benefício (0-100) ──
    teto = teto_na_data(der_base)
    if alcancaveis:
        rmi_proj = alcancaveis[0].get("rmi_projetada", Decimal("0"))
        if rmi_proj and rmi_proj > 0:
            pct_teto = min(rmi_proj / teto, Decimal("1"))
            score_valor = int(pct_teto * 100)
        else:
            score_valor = 0
    else:
        score_valor = 0

    # ── Total ──
    score_total = score_tc + score_idade + score_carencia + score_qs + score_prox + score_valor
    score_total = min(score_total, 1000)

    # Classificação
    if score_total >= 900:
        classificacao = "PRONTO"
        cor = "#00c853"
        mensagem = "Excelente! O segurado está pronto ou praticamente pronto para se aposentar."
    elif score_total >= 700:
        classificacao = "QUASE_PRONTO"
        cor = "#2196f3"
        mensagem = "Muito bom! Falta pouco para atingir todos os requisitos da aposentadoria."
    elif score_total >= 500:
        classificacao = "CAMINHO_CERTO"
        cor = "#ff9800"
        mensagem = "No caminho certo. Mantenha as contribuições para garantir a aposentadoria."
    elif score_total >= 300:
        classificacao = "ATENCAO"
        cor = "#f44336"
        mensagem = "Atenção! Ainda há um caminho considerável até a aposentadoria. Planeje-se."
    else:
        classificacao = "INICIO"
        cor = "#9e9e9e"
        mensagem = "Início da jornada previdenciária. Contribua regularmente desde já."

    # VALIDACAO ANTIALUCINACAO: score alto com dados inconsistentes
    alertas_score = []
    if score_qs == 100 and qualidade.get("status") == "PERDIDA":
        alertas_score.append("CONTRADICAO: Score de qualidade 100 mas status PERDIDA")
        score_qs = 0
        score_total = score_tc + score_idade + score_carencia + score_qs + score_prox + score_valor
        score_total = min(score_total, 1000)
        # Reclassificar
        if score_total >= 900:
            classificacao = "PRONTO"
            cor = "#00c853"
            mensagem = "O segurado atende aos requisitos de tempo e idade para aposentadoria."
        elif score_total >= 700:
            classificacao = "QUASE_PRONTO"
            cor = "#2196f3"
            mensagem = "Falta pouco para atingir todos os requisitos."
        elif score_total >= 500:
            classificacao = "CAMINHO_CERTO"
            cor = "#ff9800"
            mensagem = "No caminho certo. Mantenha as contribuicoes."
        elif score_total >= 300:
            classificacao = "ATENCAO"
            cor = "#f44336"
            mensagem = "Atencao! Ainda ha caminho consideravel ate a aposentadoria."
        else:
            classificacao = "INICIO"
            cor = "#9e9e9e"
            mensagem = "Inicio da jornada previdenciaria."

    return {
        "score": score_total,
        "maximo": 1000,
        "percentual": round(score_total / 10, 1),
        "classificacao": classificacao,
        "cor": cor,
        "mensagem": mensagem,
        "disclaimer": (
            "Este score e uma metrica INTERNA de acompanhamento. "
            "NAO tem valor juridico e NAO deve ser apresentado em peticoes ou laudos. "
            "Serve apenas como indicador visual do progresso em direcao a aposentadoria."
        ),
        "alertas": alertas_score,
        "componentes": {
            "tempo_contribuicao": {"pontos": score_tc, "maximo": 300, "detalhe": f"{tc_atual.anos}a {tc_atual.meses_restantes}m de {tc_necessario_anos}a necessarios"},
            "idade": {"pontos": score_idade, "maximo": 200, "detalhe": f"{int(idade_anos)} anos de {int(idade_min)} necessarios"},
            "carencia": {"pontos": score_carencia, "maximo": 150, "detalhe": f"{total_carencia} de 180 contribuicoes"},
            "qualidade_segurado": {"pontos": score_qs, "maximo": 100, "detalhe": status_qs},
            "proximidade": {"pontos": score_prox, "maximo": 150, "detalhe": f"{alcancaveis[0]['meses_faltantes']} meses para aposentar" if alcancaveis else "Sem projecao"},
            "valor_beneficio": {"pontos": score_valor, "maximo": 100, "detalhe": f"RMI projetada vs teto R$ {teto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")},
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TC nos Marcos Legais — igual ao Prévius, mas com análise mais completa
# ─────────────────────────────────────────────────────────────────────────────

def _tc_marcos_legais(segurado: Segurado, der_base: date) -> List[Dict[str, Any]]:
    """
    Calcula o tempo de contribuição em cada marco legal relevante.
    O Prévius mostra isso — nós também, com análise de impacto.

    Marcos:
      1. 05/10/1988 — Constituição Federal (conversão de tempo especial)
      2. 15/12/1998 — EC 20/98 (novas regras de aposentadoria)
      3. 28/11/1999 — Lei 9.876/99 (fator previdenciário, PBC desde 07/1994)
      4. 13/11/2019 — EC 103/2019 (Reforma da Previdência)
      5. DER (data atual) — situação atual
    """
    marcos = [
        {
            "data": date(1988, 10, 5),
            "nome": "Constituição Federal de 1988",
            "sigla": "CF/88",
            "relevancia": "Define direitos previdenciários fundamentais. TC anterior conta para direito adquirido.",
        },
        {
            "data": date(1998, 12, 15),
            "nome": "Emenda Constitucional nº 20/1998",
            "sigla": "EC 20/98",
            "relevancia": "Estabeleceu novas regras. TC até esta data gera direito adquirido às regras anteriores.",
        },
        {
            "data": date(1999, 11, 28),
            "nome": "Lei 9.876/1999 (Fator Previdenciário)",
            "sigla": "Lei 9.876/99",
            "relevancia": "Criou o fator previdenciário e definiu o PBC a partir de 07/1994. TC aqui define o cálculo pela regra antiga vs nova.",
        },
        {
            "data": date(2019, 11, 13),
            "nome": "EC 103/2019 (Reforma da Previdência)",
            "sigla": "EC 103/19",
            "relevancia": "Reforma radical. TC até esta data define elegibilidade para regras de transição (pedágio 50%, 100%, pontos, idade progressiva).",
        },
        {
            "data": der_base,
            "nome": f"Data de Referência ({der_base.strftime('%d/%m/%Y')})",
            "sigla": "DER",
            "relevancia": "Situação atual do segurado para análise de todas as regras vigentes.",
        },
    ]

    resultado = []
    sexo = str(segurado.sexo).upper()

    for marco in marcos:
        data_marco = marco["data"]

        # Só calcula se o segurado já tinha nascido
        if data_marco < segurado.dados_pessoais.data_nascimento:
            resultado.append({
                **marco,
                "data": data_marco.strftime("%d/%m/%Y"),
                "tc_anos": 0, "tc_meses": 0, "tc_dias": 0,
                "tc_texto": "Não nascido",
                "contribuicoes": 0,
                "idade_anos": 0,
                "observacao": "O segurado ainda não havia nascido nesta data.",
            })
            continue

        # Calcular TC até o marco
        tc = calcular_tempo_contribuicao(segurado.vinculos, data_marco, segurado.sexo, beneficios_anteriores=segurado.beneficios_anteriores)

        # Contar contribuições até o marco
        contribs_ate = 0
        for v in segurado.vinculos:
            for c in v.contribuicoes:
                if c.competencia <= data_marco:
                    contribs_ate += 1

        # Idade no marco
        idade_marco = (data_marco - segurado.dados_pessoais.data_nascimento).days // 365

        # Observação contextualizada
        obs = ""
        if marco["sigla"] == "EC 20/98":
            tc_necessario = 35 if "MASC" in sexo else 30
            if tc.anos >= tc_necessario:
                obs = f"✅ TC completo ({tc.anos}a) — direito adquirido às regras anteriores à EC 20/98."
            else:
                falta = tc_necessario - tc.anos
                obs = f"TC de {tc.anos}a (faltavam ~{falta}a para direito adquirido pré-EC 20/98)."
        elif marco["sigla"] == "Lei 9.876/99":
            if tc.anos > 0:
                obs = f"TC de {tc.anos}a {tc.meses_restantes}m — define proporção do cálculo pela regra antiga vs fator previdenciário."
            else:
                obs = "Sem TC nesta data — cálculo integralmente pela Lei 9.876/99."
        elif marco["sigla"] == "EC 103/19":
            tc_necessario = 35 if "MASC" in sexo else 30
            if tc.anos >= tc_necessario:
                obs = f"✅ TC completo ({tc.anos}a {tc.meses_restantes}m) — direito adquirido pré-reforma!"
            else:
                faltava = tc_necessario - tc.anos
                obs = f"TC de {tc.anos}a {tc.meses_restantes}m ({contribs_ate} contribuições). Faltavam ~{faltava}a — sujeito às regras de transição."
        elif marco["sigla"] == "DER":
            car = calcular_carencia(segurado.vinculos, data_marco)
            obs = f"Situação atual: {tc.anos}a {tc.meses_restantes}m {tc.dias_restantes}d ({car} contribuições)."

        resultado.append({
            "data": data_marco.strftime("%d/%m/%Y"),
            "nome": marco["nome"],
            "sigla": marco["sigla"],
            "relevancia": marco["relevancia"],
            "tc_anos": tc.anos,
            "tc_meses": tc.meses_restantes,
            "tc_dias": tc.dias_restantes,
            "tc_texto": f"{tc.anos}a {tc.meses_restantes}m {tc.dias_restantes}d",
            "contribuicoes": contribs_ate,
            "idade_anos": idade_marco,
            "observacao": obs,
        })

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Competências sem Salário — detecção automática (Prévius tem, nós também)
# ─────────────────────────────────────────────────────────────────────────────

def _competencias_sem_salarios(segurado: Segurado) -> Dict[str, Any]:
    """
    Detecta competências (meses) onde o segurado tem contribuição registrada
    mas com salário zero ou ausente. Isso pode indicar:
      - Erro no CNIS
      - Contribuição não processada pelo INSS
      - Necessidade de retificação administrativa

    O Prévius lista essas competências — nós detectamos E explicamos o impacto.
    """
    sem_salario: List[Dict[str, str]] = []
    com_salario_abaixo_minimo: List[Dict[str, str]] = []

    for v in segurado.vinculos:
        empregador = v.empregador_nome or "Empregador não identificado"
        for c in v.contribuicoes:
            comp_str = c.competencia.strftime("%m/%Y")
            if c.salario_contribuicao <= 0:
                sem_salario.append({
                    "competencia": comp_str,
                    "empregador": empregador,
                    "tipo": "SEM_SALARIO",
                })
            elif c.salario_contribuicao < Decimal("100"):
                # Valor suspeitamente baixo (pode ser erro de parsing)
                com_salario_abaixo_minimo.append({
                    "competencia": comp_str,
                    "empregador": empregador,
                    "valor": str(c.salario_contribuicao),
                    "tipo": "ABAIXO_MINIMO",
                })

    total_problemas = len(sem_salario) + len(com_salario_abaixo_minimo)

    if total_problemas == 0:
        mensagem = "✅ Todas as competências possuem salário de contribuição registrado. Nenhuma irregularidade detectada."
        impacto = "Nenhum impacto negativo detectado."
    elif len(sem_salario) > 0 and len(com_salario_abaixo_minimo) > 0:
        mensagem = (
            f"⚠️ Detectadas {len(sem_salario)} competências SEM salário de contribuição "
            f"e {len(com_salario_abaixo_minimo)} com valores abaixo do salário mínimo. "
            f"Isso pode reduzir a média salarial e o valor do benefício."
        )
        impacto = (
            "As competências sem salário podem estar sendo desconsideradas no cálculo da média. "
            "Recomenda-se solicitar retificação de dados no CNIS com documentos comprobatórios "
            "(holerites, CTPS, declaração do empregador)."
        )
    elif len(sem_salario) > 0:
        mensagem = (
            f"⚠️ Detectadas {len(sem_salario)} competências SEM salário de contribuição registrado. "
            f"Esses meses contam para tempo de contribuição, mas NÃO entram na média para cálculo da RMI."
        )
        impacto = (
            "Solicite retificação no CNIS. Se comprovado o vínculo com holerites ou CTPS, "
            "o INSS deve incluir os salários. Isso pode aumentar significativamente a RMI."
        )
    else:
        mensagem = (
            f"⚠️ Detectadas {len(com_salario_abaixo_minimo)} competências com valores suspeitamente baixos. "
            f"Verifique se são valores corretos ou erros no registro do CNIS."
        )
        impacto = "Valores abaixo do salário mínimo podem indicar erro de registro."

    return {
        "sem_salario": sem_salario,
        "abaixo_minimo": com_salario_abaixo_minimo,
        "total_problemas": total_problemas,
        "mensagem": mensagem,
        "impacto": impacto,
    }


def _analisar_especial_vinculos(segurado: Segurado) -> List[Dict]:
    """
    Analisa cada vínculo do segurado para possível atividade especial.
    Inclui busca automatizada de jurisprudência consolidada (95%+ confiança).
    """
    try:
        from ..especial.agentes_nocivos import verificar_possivel_especial
    except ImportError:
        return []

    # Importar módulo de jurisprudência
    try:
        from ..especial.jurisprudencia import buscar_jurisprudencia
    except ImportError:
        buscar_jurisprudencia = None

    analises = []
    for v in segurado.vinculos:
        if v.empregador_nome and v.empregador_nome.strip().lower() in ("projeção futura", "projecao futura"):
            continue  # Pular vínculos simulados
        resultado = verificar_possivel_especial(
            empregador_nome=v.empregador_nome or "",
            empregador_cnpj=v.empregador_cnpj or "",
        )
        # Se não encontrou pelo nome, tentar pelo cargo/CBO (da CTPS)
        cargo_ctps = ""
        if not resultado.get("possivel_especial") and v.observacao:
            import re as _re
            m = _re.search(r"Cargo CTPS:\s*(.+?)(?:\||$)", v.observacao)
            if m:
                cargo_ctps = m.group(1).strip()
                resultado_cargo = verificar_possivel_especial(
                    empregador_nome=cargo_ctps,
                    empregador_cnpj="",
                )
                if resultado_cargo.get("possivel_especial"):
                    resultado = resultado_cargo
                    resultado["via_cargo_ctps"] = True
                    resultado["cargo_ctps"] = cargo_ctps
        if resultado.get("possivel_especial"):
            # Converter agentes de dicts para strings legíveis
            agentes_raw = resultado.get("agentes_provaveis", [])
            agentes_str = []
            agentes_codigos = []
            for a in agentes_raw:
                if isinstance(a, dict):
                    agentes_str.append(a.get("descricao", a.get("codigo", str(a))))
                    agentes_codigos.append(a.get("codigo", ""))
                else:
                    agentes_str.append(str(a))
                    agentes_codigos.append(str(a))

            # Buscar jurisprudência aderente (95%+ confiança)
            jurisprudencias = []
            if buscar_jurisprudencia:
                categoria = resultado.get("categoria", "")
                juris = buscar_jurisprudencia(
                    agentes_provaveis=agentes_codigos,
                    categoria_empregador=categoria,
                    empregador_nome=v.empregador_nome or "",
                    confianca_minima=0.95,
                )
                for j in juris:
                    jurisprudencias.append({
                        "tipo": j.tipo,
                        "numero": j.numero,
                        "tribunal": j.tribunal,
                        "ementa": j.ementa,
                        "data_julgamento": j.data_julgamento or "",
                        "aplicabilidade": j.aplicabilidade,
                        "confianca": j.confianca,
                        "url": j.url or "",
                    })

            # Extrair cargo da observação para exibição
            cargo_info = cargo_ctps or ""
            if not cargo_info and v.observacao:
                import re as _re2
                m2 = _re2.search(r"Cargo CTPS:\s*(.+?)(?:\||$)", v.observacao or "")
                if m2:
                    cargo_info = m2.group(1).strip()

            analises.append({
                "empregador": v.empregador_nome,
                "cnpj": v.empregador_cnpj,
                "cargo_ctps": cargo_info,
                "via_cargo": resultado.get("via_cargo_ctps", False),
                "data_inicio": v.data_inicio.strftime("%d/%m/%Y") if v.data_inicio else None,
                "data_fim": v.data_fim.strftime("%d/%m/%Y") if v.data_fim else None,
                "probabilidade": resultado.get("probabilidade", ""),
                "agentes_provaveis": agentes_str,
                "fundamentacao": resultado.get("fundamentacao", ""),
                "recomendacao": resultado.get("recomendacao", ""),
                "fator_conversao": resultado.get("fatores_conversao", {}),
                "aposentadoria_especial_anos": resultado.get("aposentadoria_especial_anos", 25),
                "padroes_encontrados": [p.get("categoria", "") for p in resultado.get("padroes_encontrados", [])],
                "jurisprudencias": jurisprudencias,
            })
        else:
            # Extrair cargo para vínculos sem match também
            cargo_sem_match = ""
            if v.observacao:
                import re as _re3
                m3 = _re3.search(r"Cargo CTPS:\s*(.+?)(?:\||$)", v.observacao or "")
                if m3:
                    cargo_sem_match = m3.group(1).strip()
            # Incluir vínculos sem match para mostrar estudo completo
            analises.append({
                "empregador": v.empregador_nome,
                "cnpj": v.empregador_cnpj,
                "cargo_ctps": cargo_sem_match,
                "via_cargo": False,
                "data_inicio": v.data_inicio.strftime("%d/%m/%Y") if v.data_inicio else None,
                "data_fim": v.data_fim.strftime("%d/%m/%Y") if v.data_fim else None,
                "probabilidade": "NENHUMA",
                "agentes_provaveis": [],
                "fundamentacao": "",
                "recomendacao": resultado.get("recomendacao", "Sem indícios pelo nome. Verificar função exercida e solicitar PPP se houver suspeita."),
                "fator_conversao": {},
                "aposentadoria_especial_anos": 0,
                "padroes_encontrados": [],
                "jurisprudencias": [],
            })
    return analises


def _gerar_memoria(segurado: Segurado, der: date) -> Dict:
    """Gera memória de cálculo com correção monetária."""
    try:
        from ..calculo.memoria_calculo import gerar_memoria_calculo
    except ImportError:
        return {}

    contribuicoes = []
    for v in segurado.vinculos:
        for c in v.contribuicoes:
            contribuicoes.append({
                "competencia": c.competencia,
                "salario": c.salario_contribuicao,
                "vinculo_nome": v.empregador_nome or "",
            })

    if not contribuicoes:
        return {}

    return gerar_memoria_calculo(contribuicoes, der)
