"""
Motor de contagem de tempo de contribuição.

REGRAS CRÍTICAS (Decreto 3.048/99 e alterações):
1. EMPREGADO/AVULSO/DOMÉSTICO: TC conta em DIAS CORRIDOS (Art. 60 Decreto 3.048/99)
   Período: data_inicio até min(data_fim, DER), inclusive ambas as datas
2. FACULTATIVO/CI/MEI: TC conta por COMPETÊNCIAS com contribuição válida
   Cada mês com contribuição válida = 30 dias (Art. 19-C Decreto 10.410/2020)
   Contribuições abaixo do salário mínimo NÃO contam (Art. 19-E Decreto 3.048/99)
3. Sobreposição de vínculos NÃO duplica o tempo — conta-se apenas uma vez
4. Auxílio-doença (espécie 31/91) INTERCALADO com contribuições conta como TC,
   mas NÃO conta como carência (Art. 60 §§ 3º e 4º Lei 8.213/91)
5. Tempo especial é CONVERTIDO para comum com o fator correspondente
6. Indicadores do CNIS (PREC-MENOR-MIN, IREC-INDPEND, IREC-LC123) excluem períodos
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Optional, Set

from ..models.periodo import Periodo, PeriodoEspecial, TempoContribuicao
from ..models.vinculo import Vinculo
from ..models.segurado import BeneficioAnterior
from ..enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, Sexo, TipoBeneficio
from ..constantes import DatasCorte, FATORES_CONVERSAO, DATA_LIMITE_CONVERSAO_ESPECIAL
from ..indices.salario_minimo import salario_minimo_em


# ─────────────────────────────────────────────────────────────────────────────
# Indicadores CNIS que invalidam contribuições / períodos
# ─────────────────────────────────────────────────────────────────────────────
INDICADORES_EXCLUI_TC = {
    "PREC-MENOR-MIN",   # Recolhimento abaixo do salário mínimo (Art. 19-E)
    "PREC-FACULTCONC",  # Facultativo concomitante com obrigatória (não acumula)
}
# Indicadores INFORMATIVOS que NÃO excluem:
# IREC-INDPEND: pendência administrativa — comum, geralmente regularizável
# IREC-LC123: recolhimento via Simples Nacional — válido
# IREM-INDPAM: informativo, não invalida contribuição
# AEXT-VI: acerto extemporâneo — contribuição válida após regularização

INDICADORES_EXCLUI_CARENCIA = INDICADORES_EXCLUI_TC | {
    "PREC-MENOR-QTD",   # Recolhimento com quantidade menor que esperada
}

# Tipos de vínculo que contam TC por período (data_inicio a data_fim)
TIPOS_CONTAGEM_POR_PERIODO = {
    TipoVinculo.EMPREGADO,
    TipoVinculo.EMPREGADO_DOMESTICO,
    TipoVinculo.TRABALHADOR_AVULSO,
    TipoVinculo.SERVICO_MILITAR,
    TipoVinculo.DIRIGENTE_SINDICAL,
    TipoVinculo.RURAL_BOIA_FRIA,
    TipoVinculo.SEGURADO_ESPECIAL,
}

# Tipos que contam TC por contribuições efetivas (mês a mês)
TIPOS_CONTAGEM_POR_CONTRIBUICAO = {
    TipoVinculo.FACULTATIVO,
    TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
    TipoVinculo.MEI,
}


def calcular_tempo_contribuicao(
    vinculos: List[Vinculo],
    der: date,
    sexo: Sexo,
    incluir_especial: bool = True,
    beneficios_anteriores: Optional[List[BeneficioAnterior]] = None,
) -> TempoContribuicao:
    """
    Calcula o tempo de contribuição total do segurado até a DER.

    Processo (conforme Decreto 3.048/99 e Decreto 10.410/2020):
    1. Para EMPREGADO/AVULSO/DOMÉSTICO: conta dias corridos do período
    2. Para FACULTATIVO/CI/MEI: conta apenas competências com contribuição válida (30d/mês)
    3. Aplica exclusões por indicadores CNIS
    4. Aplica Art. 19-E (contribuições abaixo do mínimo pós-EC 103/2019)
    5. Inclui auxílio-doença intercalado como TC
    6. Remove sobreposições
    7. Converte períodos especiais para tempo comum

    Retorna TempoContribuicao com dias_total, dias_comum e dias_especial_convertido.
    """
    # ── 1. Extrair períodos de vínculos por tipo ─────────────────────────────
    periodos_normais: List[Periodo] = []
    periodos_especiais: List[PeriodoEspecial] = []
    competencias_validas_ci: Set[date] = set()  # Para CI/FACULT, rastrear meses válidos

    for v in vinculos:
        if v.regime != RegimePrevidenciario.RGPS:
            continue  # RPPS é tratado separadamente

        # Verificar indicadores do vínculo que excluem completamente
        if _vinculo_excluido_por_indicadores(v):
            continue

        if v.tipo_vinculo in TIPOS_CONTAGEM_POR_PERIODO:
            # EMPREGADO/AVULSO/DOMÉSTICO: conta por período
            _processar_vinculo_periodo(v, der, sexo, incluir_especial,
                                       periodos_normais, periodos_especiais)
        elif v.tipo_vinculo in TIPOS_CONTAGEM_POR_CONTRIBUICAO:
            # FACULTATIVO/CI/MEI: conta por contribuição efetiva
            if v.tipo_atividade != TipoAtividade.NORMAL and incluir_especial:
                # Especial: processar separadamente para aplicar fator de conversão
                _processar_vinculo_contribuicao_especial(
                    v, der, sexo, periodos_especiais
                )
            else:
                _processar_vinculo_contribuicao(v, der, competencias_validas_ci)
        else:
            # Fallback: se tem contribuições, conta por elas; senão, por período
            if v.contribuicoes:
                if v.tipo_atividade != TipoAtividade.NORMAL and incluir_especial:
                    _processar_vinculo_contribuicao_especial(
                        v, der, sexo, periodos_especiais
                    )
                else:
                    _processar_vinculo_contribuicao(v, der, competencias_validas_ci)
            else:
                _processar_vinculo_periodo(v, der, sexo, incluir_especial,
                                           periodos_normais, periodos_especiais)

    # ── 2. Incluir auxílio-doença intercalado como TC ────────────────────────
    if beneficios_anteriores:
        periodos_auxilio = _periodos_auxilio_doenca_intercalados(
            beneficios_anteriores, vinculos, der
        )
        periodos_normais.extend(periodos_auxilio)

    # ── 3. Converter competências CI/FACULT em períodos de 30 dias ──────────
    # Cada competência válida = 30 dias, conforme Art. 19-C Decreto 10.410/2020
    periodos_ci = _competencias_para_periodos(sorted(competencias_validas_ci))
    periodos_normais.extend(periodos_ci)

    # ── 4. Remover sobreposições ─────────────────────────────────────────────
    periodos_normais_sem_sobreposicao = _remover_sobreposicoes(periodos_normais)

    # ── 5. Calcular dias com resolução de especiais ─────────────────────────
    dias_comum, dias_especial_convertido = _calcular_dias_precisos(
        periodos_normais_sem_sobreposicao, periodos_especiais, sexo
    )

    return TempoContribuicao(
        dias_total=dias_comum + dias_especial_convertido,
        dias_comum=dias_comum,
        dias_especial_convertido=dias_especial_convertido,
    )


def _vinculo_excluido_por_indicadores(v: Vinculo) -> bool:
    """Verifica se o vínculo inteiro deve ser excluído com base nos indicadores."""
    if not v.indicadores:
        return False
    indicadores = {ind.strip().upper() for ind in v.indicadores.split(",") if ind.strip()}
    # Se TODOS os indicadores são excludentes, o vínculo inteiro é excluído
    # Se apenas alguns, as contribuições individuais serão avaliadas
    return bool(indicadores) and indicadores.issubset(INDICADORES_EXCLUI_TC)


def _processar_vinculo_periodo(
    v: Vinculo,
    der: date,
    sexo: Sexo,
    incluir_especial: bool,
    periodos_normais: List[Periodo],
    periodos_especiais: List[PeriodoEspecial],
):
    """Processa vínculo que conta TC por período (EMPREGADO, AVULSO, DOMÉSTICO)."""
    inicio = v.data_inicio
    fim = min(v.data_fim_efetiva, der)

    if inicio > fim:
        return

    if v.tipo_atividade == TipoAtividade.NORMAL or not incluir_especial:
        periodos_normais.append(Periodo(inicio, fim, v.tipo_atividade))
    else:
        fator = _fator_conversao(v.tipo_atividade, sexo, inicio)
        pe = PeriodoEspecial(inicio, fim, v.tipo_atividade, fator_conversao=fator)
        pe.dias_convertidos = pe.converter()
        periodos_especiais.append(pe)


def _processar_vinculo_contribuicao(
    v: Vinculo,
    der: date,
    competencias_validas: Set[date],
):
    """
    Processa vínculo que conta TC por contribuição efetiva (FACULTATIVO, CI, MEI).

    Regras aplicadas:
    - Art. 19-E Decreto 3.048/99: Pós-EC 103/2019, contribuição abaixo do
      salário mínimo NÃO conta para TC nem carência
    - Cada competência com contribuição válida = 30 dias de TC
    - Indicadores do CNIS podem invalidar contribuições
    """
    for c in v.contribuicoes:
        if c.competencia > der:
            continue

        # Verificar se contribuição é válida para TC
        if not c.valida_tc:
            continue

        # Art. 19-E: Contribuições abaixo do salário mínimo
        # Para FACULTATIVO/CI, o CNIS mostra o VALOR PAGO (ex: R$133 = 11% de R$1.212),
        # NÃO o salário de contribuição (base). O indicador PREC-MENOR-MIN é a forma
        # correta de detectar contribuição abaixo do mínimo. Se o CNIS não marcou
        # PREC-MENOR-MIN, a contribuição é válida.
        # A checagem por valor já é feita pelo parser via indicadores CNIS.

        competencias_validas.add(c.competencia)


def _processar_vinculo_contribuicao_especial(
    v: Vinculo,
    der: date,
    sexo: Sexo,
    periodos_especiais: List[PeriodoEspecial],
):
    """
    Processa vínculo CI/FACULT/MEI marcado como atividade especial.

    A conversão de tempo especial se aplica independentemente do tipo de vínculo
    (Art. 66 Decreto 3.048/99). Um contribuinte individual que trabalha exposto a
    agentes nocivos (ex: dentista, eletricista autônomo) tem direito à conversão
    do período especial em comum, com o fator correspondente.
    """
    competencias_especiais: List[date] = []
    for c in v.contribuicoes:
        if c.competencia > der:
            continue
        if not c.valida_tc:
            continue
        competencias_especiais.append(c.competencia)

    if not competencias_especiais:
        return

    competencias_especiais.sort()

    # Agrupar competências consecutivas em períodos
    grupo_inicio = competencias_especiais[0]
    grupo_fim = competencias_especiais[0]

    for i in range(1, len(competencias_especiais)):
        comp = competencias_especiais[i]
        prev = competencias_especiais[i - 1]

        if (comp.year == prev.year and comp.month == prev.month + 1) or \
           (comp.year == prev.year + 1 and comp.month == 1 and prev.month == 12):
            grupo_fim = comp
        else:
            # Fechar grupo como período especial
            fator = _fator_conversao(v.tipo_atividade, sexo, grupo_inicio)
            pe = PeriodoEspecial(
                grupo_inicio, _ultimo_dia_mes(grupo_fim),
                v.tipo_atividade, fator_conversao=fator,
            )
            pe.dias_convertidos = pe.converter()
            periodos_especiais.append(pe)
            grupo_inicio = comp
            grupo_fim = comp

    # Fechar último grupo
    fator = _fator_conversao(v.tipo_atividade, sexo, grupo_inicio)
    pe = PeriodoEspecial(
        grupo_inicio, _ultimo_dia_mes(grupo_fim),
        v.tipo_atividade, fator_conversao=fator,
    )
    pe.dias_convertidos = pe.converter()
    periodos_especiais.append(pe)


def _competencias_para_periodos(competencias: List[date]) -> List[Periodo]:
    """
    Converte uma lista de competências (meses) em períodos de 30 dias cada.

    Meses consecutivos são agrupados em períodos contínuos.
    Art. 19-C Decreto 10.410/2020: contagem por mês completo.

    Exemplo: [01/2020, 02/2020, 04/2020] → 2 períodos:
      - 01/01/2020 a 28/02/2020 (59 dias, mas seriam 2 meses = 60 dias em contagem mensal)
      - 01/04/2020 a 30/04/2020 (30 dias = 1 mês)

    Para precisão compatível com Prévius/INSS, usamos a contagem dia-a-dia
    com meses completos (primeiro ao último dia de cada mês).
    """
    if not competencias:
        return []

    periodos = []
    grupo_inicio = competencias[0]
    grupo_fim = competencias[0]

    for i in range(1, len(competencias)):
        comp = competencias[i]
        prev = competencias[i - 1]

        # Verificar se é mês seguinte consecutivo
        if (comp.year == prev.year and comp.month == prev.month + 1) or \
           (comp.year == prev.year + 1 and comp.month == 1 and prev.month == 12):
            grupo_fim = comp
        else:
            # Fechar grupo anterior
            periodos.append(Periodo(
                grupo_inicio,
                _ultimo_dia_mes(grupo_fim),
                TipoAtividade.NORMAL,
            ))
            grupo_inicio = comp
            grupo_fim = comp

    # Fechar último grupo
    periodos.append(Periodo(
        grupo_inicio,
        _ultimo_dia_mes(grupo_fim),
        TipoAtividade.NORMAL,
    ))

    return periodos


def _ultimo_dia_mes(d: date) -> date:
    """Retorna o último dia do mês de uma data."""
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _periodos_auxilio_doenca_intercalados(
    beneficios: List[BeneficioAnterior],
    vinculos: List[Vinculo],
    der: date,
) -> List[Periodo]:
    """
    Identifica períodos de auxílio-doença (espécie 31/91) que contam como TC.

    Art. 60 §§ 3º e 4º Lei 8.213/91:
    O período de recebimento de auxílio-doença será computado como TC
    quando intercalado com períodos de atividade.

    STJ Tema 998 / Súmula 73 TNU:
    Basta que haja atividade ANTES do benefício (a exigência de atividade
    posterior foi flexibilizada pela jurisprudência consolidada).
    Para benefícios CESSADOS, presume-se retorno à atividade.

    Benefícios ATIVOS (em gozo) NÃO contam — o segurado ainda está afastado.
    """
    periodos = []

    # Espécies de auxílio-doença/incapacidade que contam como TC quando intercalados
    especies_auxilio = {
        TipoBeneficio.AUXILIO_DOENCA_PREV,   # B31
        TipoBeneficio.AUXILIO_DOENCA_ACID,   # B91
    }

    for b in beneficios:
        if b.especie not in especies_auxilio:
            continue
        if b.dib is None:
            continue

        dib = b.dib
        dcb = b.dcb
        if dcb is None:
            # Benefício ATIVO — não conta como TC (ainda está afastado)
            continue
        dcb = min(dcb, der)

        if dib > der:
            continue

        # Verificar se houve atividade ANTES do benefício
        tem_antes = False

        for v in vinculos:
            if v.regime != RegimePrevidenciario.RGPS:
                continue
            # Vínculo que começou antes do início do auxílio
            if v.data_inicio < dib:
                tem_antes = True
                break
            # Contribuição antes do início do auxílio
            for c in v.contribuicoes:
                if c.competencia < date(dib.year, dib.month, 1):
                    tem_antes = True
                    break
            if tem_antes:
                break

        if tem_antes:
            periodos.append(Periodo(
                dib, dcb, TipoAtividade.NORMAL,
                observacao="AUXÍLIO-DOENÇA INTERCALADO (Art. 60 §3º Lei 8.213/91 + STJ Tema 998)"
            ))

    return periodos


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de dias com resolução de sobreposições e especiais
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_dias_precisos(
    periodos_normais: List[Periodo],
    periodos_especiais: List[PeriodoEspecial],
    sexo: Sexo,
) -> Tuple[int, int]:
    """
    Calcula os dias com precisão resolvendo todas as sobreposições.
    Retorna (dias_comum, dias_especial_convertido).
    """
    if not periodos_especiais:
        # Sem períodos especiais: somar dias dos períodos normais (já sem sobreposição)
        total = sum(p.dias for p in periodos_normais)
        return total, 0

    # Com especiais: resolver sobreposição entre normal e especial
    periodos_normais_limpos = _remover_sobreposicoes(periodos_normais)
    periodos_especiais_sem_overlap = _remover_sobreposicoes(
        [Periodo(pe.data_inicio, pe.data_fim) for pe in periodos_especiais]
    )

    # Dias normais excluindo os cobertos por especiais
    dias_comum_total = 0
    for p in periodos_normais_limpos:
        dias = _dias_liquidos(p, periodos_especiais_sem_overlap)
        dias_comum_total += dias

    # Dias especiais com fator — respeitando limite EC 103/2019 (13/11/2019)
    # Apenas dias ATÉ a data limite são convertidos; dias APÓS contam em 1:1
    dias_especial_total = Decimal("0")
    for p_especial in periodos_especiais_sem_overlap:
        fator = _obter_fator_para_periodo(p_especial, periodos_especiais)
        if p_especial.data_fim <= DATA_LIMITE_CONVERSAO_ESPECIAL:
            # Todo o período é conversível
            dias_especial_total += Decimal(str(p_especial.dias)) * fator
        elif p_especial.data_inicio > DATA_LIMITE_CONVERSAO_ESPECIAL:
            # Nenhum dia é conversível — conta em 1:1
            dias_especial_total += Decimal(str(p_especial.dias))
        else:
            # Período misto: split na data limite
            dias_antes = (DATA_LIMITE_CONVERSAO_ESPECIAL - p_especial.data_inicio).days + 1
            dias_depois = (p_especial.data_fim - DATA_LIMITE_CONVERSAO_ESPECIAL).days
            dias_especial_total += Decimal(str(dias_antes)) * fator + Decimal(str(dias_depois))

    dias_especial_int = int(dias_especial_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return dias_comum_total, dias_especial_int


def _remover_sobreposicoes(periodos: List[Periodo]) -> List[Periodo]:
    """
    Remove sobreposições entre períodos, mesclando os que se tocam ou sobrepõem.
    Retorna lista de períodos sem sobreposição, ordenados.
    """
    if not periodos:
        return []

    ordenados = sorted(periodos, key=lambda p: p.data_inicio)
    resultado: List[Periodo] = [ordenados[0]]

    for atual in ordenados[1:]:
        ultimo = resultado[-1]
        # Se atual começa antes do fim do último (sobreposição ou adjacência)
        if atual.data_inicio <= _proximo_dia(ultimo.data_fim):
            # Mesclar: estender o fim se necessário
            novo_fim = max(ultimo.data_fim, atual.data_fim)
            resultado[-1] = Periodo(ultimo.data_inicio, novo_fim, ultimo.tipo_atividade)
        else:
            resultado.append(atual)

    return resultado


def _dias_liquidos(periodo: Periodo, excluir: List[Periodo]) -> int:
    """Calcula os dias de um período excluindo os cobertos pela lista `excluir`."""
    dias = periodo.dias
    for excl in excluir:
        inicio_inter = max(periodo.data_inicio, excl.data_inicio)
        fim_inter = min(periodo.data_fim, excl.data_fim)
        if inicio_inter <= fim_inter:
            dias -= (fim_inter - inicio_inter).days + 1
    return max(0, dias)


def _dias_sem_sobreposicao_com_especiais(
    periodo: Periodo, especiais: List[PeriodoEspecial]
) -> int:
    """Dias de um período normal após remover sobreposição com especiais."""
    dias = periodo.dias
    for pe in especiais:
        inicio_inter = max(periodo.data_inicio, pe.data_inicio)
        fim_inter = min(periodo.data_fim, pe.data_fim)
        if inicio_inter <= fim_inter:
            dias -= (fim_inter - inicio_inter).days + 1
    return max(0, dias)


def _obter_fator_para_periodo(
    periodo: Periodo,
    periodos_especiais_originais: List[PeriodoEspecial]
) -> Decimal:
    """Obtém o fator de conversão para um período especial."""
    for pe in periodos_especiais_originais:
        if pe.data_inicio <= periodo.data_inicio and pe.data_fim >= periodo.data_fim:
            return pe.fator_conversao
        if pe.data_inicio == periodo.data_inicio:
            return pe.fator_conversao
    return Decimal("1")


def _fator_conversao(
    tipo: TipoAtividade,
    sexo: Sexo,
    data_inicio: date,
) -> Decimal:
    """
    Retorna o fator de conversão de tempo especial para tempo comum.
    Conforme Decreto 3.048/99 Art. 70.
    """
    chave = (tipo.value, sexo.value)
    fator = FATORES_CONVERSAO.get(chave, Decimal("1"))
    return fator


def _proximo_dia(d: date) -> date:
    return d + timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# CARÊNCIA
# ─────────────────────────────────────────────────────────────────────────────

def calcular_carencia(
    vinculos: List[Vinculo],
    der: date,
    beneficios_anteriores: Optional[List[BeneficioAnterior]] = None,
) -> int:
    """
    Conta o número de competências válidas para carência.

    REGRA: Carência é contada em MESES COM CONTRIBUIÇÃO VÁLIDA,
           não em dias corridos. Uma competência com qualquer
           contribuição válida conta como 1 mês de carência.

    Para EMPREGADO (CLT): cada mês dentro do período do vínculo conta
    como carência, MESMO que não haja remuneração registrada no CNIS
    (presunção de recolhimento pelo empregador — Súmula 75 TNU).

    Para CI/FACULTATIVO/MEI: conta apenas meses com contribuição efetiva.
    Pós-EC 103/2019: contribuições abaixo do mínimo NÃO contam (Art. 19-E).

    NOTA: Auxílio-doença NÃO conta para carência (Art. 29 §5 Lei 8.213/91).
    """
    competencias_validas = set()

    for v in vinculos:
        if v.regime != RegimePrevidenciario.RGPS:
            continue

        if v.tipo_vinculo in TIPOS_CONTAGEM_POR_PERIODO:
            # EMPREGADO/AVULSO/DOMÉSTICO: conta meses do período como carência
            # Mesmo sem salário registrado (Súmula 75 TNU)
            inicio = v.data_inicio
            fim = min(v.data_fim_efetiva, der)
            if inicio > fim:
                continue

            # Gerar todas as competências do período
            comp = date(inicio.year, inicio.month, 1)
            fim_comp = date(fim.year, fim.month, 1)
            while comp <= fim_comp:
                competencias_validas.add(comp)
                if comp.month == 12:
                    comp = date(comp.year + 1, 1, 1)
                else:
                    comp = date(comp.year, comp.month + 1, 1)

            # Se tem contribuições explícitas, adicionar também
            for c in v.contribuicoes:
                if c.competencia > der:
                    continue
                if c.valida_carencia:
                    competencias_validas.add(c.competencia)

        else:
            # FACULTATIVO/CI/MEI: conta apenas contribuições explícitas válidas
            # Art. 19-E já é tratado pelo indicador PREC-MENOR-MIN no parser
            for c in v.contribuicoes:
                if c.competencia > der:
                    continue
                if not c.valida_carencia:
                    continue
                competencias_validas.add(c.competencia)

    return len(competencias_validas)


# ─────────────────────────────────────────────────────────────────────────────
# Identificação de sobreposições (para alertar o usuário)
# ─────────────────────────────────────────────────────────────────────────────

def identificar_sobreposicoes(vinculos: List[Vinculo]) -> List[Tuple[Vinculo, Vinculo, date, date]]:
    """
    Identifica sobreposições entre vínculos (para alertar o usuário).
    Retorna lista de (vinculo1, vinculo2, data_inicio_sobreposicao, data_fim_sobreposicao).
    """
    sobreposicoes = []
    for i in range(len(vinculos)):
        for j in range(i + 1, len(vinculos)):
            v1, v2 = vinculos[i], vinculos[j]
            inicio_s = max(v1.data_inicio, v2.data_inicio)
            fim_s = min(v1.data_fim_efetiva, v2.data_fim_efetiva)
            if inicio_s <= fim_s:
                sobreposicoes.append((v1, v2, inicio_s, fim_s))
    return sobreposicoes
