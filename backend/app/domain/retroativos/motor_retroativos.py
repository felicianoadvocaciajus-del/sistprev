"""
Motor de Calculo de Retroativos Previdenciarios.

Calcula valores devidos pelo INSS ao segurado nos casos de:
  - Concessao tardia (INSS demorou para conceder)
  - Revisao de beneficio (recalculo com RMI maior)
  - Indeferimento indevido (beneficio deveria ter sido concedido)

Cada centavo e rastreavel: a memoria de calculo detalha parcela a parcela
o valor bruto, a correcao monetaria (INPC), os juros de mora e o regime
juridico aplicavel.

Fundamentacao legal:
  - Correcao monetaria: INPC (Lei 8.213/91, Art. 41-A)
  - Juros de mora ate 06/2009: 1% a.m. (Lei 9.494/97)
  - Juros de mora 07/2009 a 11/2021: poupanca/SELIC (Lei 11.960/09)
  - Juros de mora a partir de 12/2021: SELIC (EC 113/2021)
  - Prescricao quinquenal: Sumula 85/STJ; Decreto 20.910/32
  - Teto e piso: Art. 33 Lei 8.213/91; Art. 201 §2 CF/88
  - 13o salario: Lei 8.213/91, Art. 40
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constantes e tabelas simplificadas
# ---------------------------------------------------------------------------

# INPC anual simplificado (mesma abordagem de memoria_calculo.py)
INPC_ANUAL: Dict[int, Decimal] = {
    1994: Decimal("22.41"), 1995: Decimal("22.41"), 1996: Decimal("9.12"),
    1997: Decimal("4.34"),  1998: Decimal("2.49"),  1999: Decimal("8.43"),
    2000: Decimal("5.27"),  2001: Decimal("9.44"),  2002: Decimal("14.74"),
    2003: Decimal("10.38"), 2004: Decimal("6.13"),  2005: Decimal("5.05"),
    2006: Decimal("2.81"),  2007: Decimal("5.15"),  2008: Decimal("6.48"),
    2009: Decimal("4.11"),  2010: Decimal("6.47"),  2011: Decimal("6.08"),
    2012: Decimal("6.20"),  2013: Decimal("5.56"),  2014: Decimal("6.23"),
    2015: Decimal("11.28"), 2016: Decimal("6.58"),  2017: Decimal("2.07"),
    2018: Decimal("3.43"),  2019: Decimal("4.48"),  2020: Decimal("5.45"),
    2021: Decimal("10.16"), 2022: Decimal("5.93"),  2023: Decimal("3.71"),
    2024: Decimal("4.77"),  2025: Decimal("4.50"),  2026: Decimal("4.00"),
}

# SELIC anual simplificada (para calculo de juros de mora pos Lei 11.960/09)
SELIC_ANUAL: Dict[int, Decimal] = {
    2009: Decimal("9.92"),  2010: Decimal("9.78"),  2011: Decimal("11.62"),
    2012: Decimal("8.49"),  2013: Decimal("8.22"),  2014: Decimal("10.90"),
    2015: Decimal("13.24"), 2016: Decimal("14.00"), 2017: Decimal("9.93"),
    2018: Decimal("6.40"),  2019: Decimal("5.96"),  2020: Decimal("2.76"),
    2021: Decimal("4.42"),  2022: Decimal("12.39"), 2023: Decimal("13.04"),
    2024: Decimal("10.81"), 2025: Decimal("14.25"), 2026: Decimal("12.00"),
}

# Teto INSS por ano (simplificado — valor vigente em janeiro de cada ano)
TETO_INSS: Dict[int, Decimal] = {
    1994: Decimal("582.86"),   1995: Decimal("832.66"),
    1996: Decimal("957.56"),   1997: Decimal("1031.87"),
    1998: Decimal("1081.50"),  1999: Decimal("1255.32"),
    2000: Decimal("1328.25"),  2001: Decimal("1430.00"),
    2002: Decimal("1561.56"),  2003: Decimal("1869.34"),
    2004: Decimal("2508.72"),  2005: Decimal("2668.15"),
    2006: Decimal("2801.56"),  2007: Decimal("2894.28"),
    2008: Decimal("3038.99"),  2009: Decimal("3218.90"),
    2010: Decimal("3467.40"),  2011: Decimal("3689.66"),
    2012: Decimal("3916.20"),  2013: Decimal("4159.00"),
    2014: Decimal("4390.24"),  2015: Decimal("4663.75"),
    2016: Decimal("5189.82"),  2017: Decimal("5531.31"),
    2018: Decimal("5645.80"),  2019: Decimal("5839.45"),
    2020: Decimal("6101.06"),  2021: Decimal("6433.57"),
    2022: Decimal("7087.22"),  2023: Decimal("7507.49"),
    2024: Decimal("7786.02"),  2025: Decimal("8157.41"),
    2026: Decimal("8500.00"),
}

# Salario minimo por ano (piso do beneficio)
SALARIO_MINIMO: Dict[int, Decimal] = {
    1994: Decimal("70.00"),    1995: Decimal("100.00"),
    1996: Decimal("112.00"),   1997: Decimal("120.00"),
    1998: Decimal("130.00"),   1999: Decimal("136.00"),
    2000: Decimal("151.00"),   2001: Decimal("180.00"),
    2002: Decimal("200.00"),   2003: Decimal("240.00"),
    2004: Decimal("260.00"),   2005: Decimal("300.00"),
    2006: Decimal("350.00"),   2007: Decimal("380.00"),
    2008: Decimal("415.00"),   2009: Decimal("465.00"),
    2010: Decimal("510.00"),   2011: Decimal("545.00"),
    2012: Decimal("622.00"),   2013: Decimal("678.00"),
    2014: Decimal("724.00"),   2015: Decimal("788.00"),
    2016: Decimal("880.00"),   2017: Decimal("937.00"),
    2018: Decimal("954.00"),   2019: Decimal("998.00"),
    2020: Decimal("1045.00"),  2021: Decimal("1100.00"),
    2022: Decimal("1212.00"),  2023: Decimal("1320.00"),
    2024: Decimal("1412.00"),  2025: Decimal("1518.00"),
    2026: Decimal("1600.00"),
}

_QUANTIZE_2 = Decimal("0.01")
_QUANTIZE_6 = Decimal("0.000001")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWELVE = Decimal("12")
_HUNDRED = Decimal("100")

# ---------------------------------------------------------------------------
# Marcos legais para juros de mora
# ---------------------------------------------------------------------------
_INICIO_LEI_11960 = date(2009, 7, 1)
_INICIO_EC_113 = date(2021, 12, 1)


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class ParcelaRetroativa:
    """Uma parcela mensal do calculo de retroativos."""
    competencia: date
    rmi_devida: Decimal
    rmi_paga: Decimal               # 0 se o beneficio foi indeferido
    diferenca_bruta: Decimal
    correcao_monetaria: Decimal
    juros_mora: Decimal
    valor_corrigido: Decimal
    valor_com_juros: Decimal
    indice_correcao: str            # indice utilizado (ex. "INPC")
    taxa_juros: str                 # regime de juros (ex. "1% a.m. — Lei 9.494/97")
    prescrita: bool = False         # True se atingida pela prescricao quinquenal


@dataclass
class ResultadoRetroativos:
    """Resultado consolidado do calculo de retroativos."""
    dib: date
    dip: date
    der: date
    data_calculo: date
    rmi_original: Decimal
    rmi_corrigida: Decimal
    diferenca_mensal: Decimal
    total_bruto: Decimal
    total_corrigido: Decimal
    total_juros: Decimal
    total_liquido: Decimal          # corrigido + juros - abatimento
    abatimento: Decimal
    parcelas: List[ParcelaRetroativa]
    parcelas_prescritas: int
    valor_prescrito: Decimal
    valor_13os: Decimal
    memoria_calculo: List[str]
    disclaimer: str


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _q2(v: Decimal) -> Decimal:
    """Arredonda para 2 casas decimais (centavos)."""
    return v.quantize(_QUANTIZE_2, rounding=ROUND_HALF_UP)


def _teto_no_mes(comp: date) -> Decimal:
    """Retorna o teto do INSS vigente na competencia."""
    return TETO_INSS.get(comp.year, Decimal("8500.00"))


def _piso_no_mes(comp: date) -> Decimal:
    """Retorna o salario minimo vigente na competencia."""
    return SALARIO_MINIMO.get(comp.year, Decimal("1600.00"))


def _aplicar_teto_e_piso(valor: Decimal, comp: date) -> Decimal:
    """Limita o valor ao teto e garante o piso."""
    teto = _teto_no_mes(comp)
    piso = _piso_no_mes(comp)
    if valor > teto:
        return teto
    if valor < piso:
        return piso
    return valor


def _gerar_competencias(inicio: date, fim: date) -> List[date]:
    """Gera lista de competencias (primeiro dia de cada mes) entre inicio e fim."""
    competencias: List[date] = []
    atual = date(inicio.year, inicio.month, 1)
    fim_normalizado = date(fim.year, fim.month, 1)
    while atual <= fim_normalizado:
        competencias.append(atual)
        # Proximo mes
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)
    return competencias


def _meses_entre(d1: date, d2: date) -> int:
    """Numero de meses entre duas datas (d2 >= d1)."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _eh_mes_13(comp: date) -> bool:
    """Verifica se a competencia e dezembro (mes de pagamento do 13o)."""
    return comp.month == 12


# ---------------------------------------------------------------------------
# Correcao monetaria (INPC)
# ---------------------------------------------------------------------------

def calcular_correcao_monetaria(
    valor: Decimal,
    data_origem: date,
    data_destino: date,
) -> Tuple[Decimal, Decimal]:
    """
    Corrige monetariamente um valor pelo INPC, de data_origem ate data_destino.

    Retorna:
        (valor_corrigido, indice_acumulado)

    O indice e calculado pela composicao mensal proporcional das taxas anuais,
    seguindo a mesma metodologia simplificada de memoria_calculo.py.
    """
    if data_destino <= data_origem:
        return (_q2(valor), _ONE)

    indice = _ONE
    ano_inicio = data_origem.year
    ano_fim = data_destino.year

    for ano in range(ano_inicio, ano_fim + 1):
        taxa_anual = INPC_ANUAL.get(ano, Decimal("4.00"))
        taxa_mensal = taxa_anual / _HUNDRED / _TWELVE

        if ano == ano_inicio and ano == ano_fim:
            meses = data_destino.month - data_origem.month
            if meses <= 0:
                meses = 1
        elif ano == ano_inicio:
            meses = 12 - data_origem.month + 1
        elif ano == ano_fim:
            meses = data_destino.month
        else:
            meses = 12

        for _ in range(meses):
            indice *= (_ONE + taxa_mensal)

    indice = indice.quantize(_QUANTIZE_6, rounding=ROUND_HALF_UP)
    valor_corrigido = _q2(valor * indice)

    return (valor_corrigido, indice)


# ---------------------------------------------------------------------------
# Juros de mora
# ---------------------------------------------------------------------------

def _regime_juros(data_ref: date) -> str:
    """Identifica o regime de juros aplicavel na data de referencia."""
    if data_ref < _INICIO_LEI_11960:
        return "1_pct_mes"
    elif data_ref < _INICIO_EC_113:
        return "selic_lei_11960"
    else:
        return "selic_ec_113"


def _descricao_regime_juros(regime: str) -> str:
    """Descricao legivel do regime de juros."""
    descricoes = {
        "1_pct_mes": "1% a.m. (Lei 9.494/97)",
        "selic_lei_11960": "SELIC — poupanca (Lei 11.960/09)",
        "selic_ec_113": "SELIC (EC 113/2021)",
    }
    return descricoes.get(regime, regime)


def calcular_juros_mora(
    valor: Decimal,
    data_citacao: date,
    data_calculo: date,
) -> Tuple[Decimal, Decimal]:
    """
    Calcula juros de mora sobre um valor, da data de citacao ate a data do calculo.

    O calculo respeita as transicoes de regime:
      - Ate 06/2009: 1% ao mes (simples) — Lei 9.494/97
      - 07/2009 a 11/2021: SELIC (Lei 11.960/09, art. 1o-F)
      - 12/2021 em diante: SELIC (EC 113/2021)

    Retorna:
        (valor_juros, taxa_acumulada_percentual)
    """
    if data_calculo <= data_citacao:
        return (_ZERO, _ZERO)

    juros_total = _ZERO

    # Gera cada mes entre citacao e calculo
    comp_atual = date(data_citacao.year, data_citacao.month, 1)
    comp_fim = date(data_calculo.year, data_calculo.month, 1)

    while comp_atual <= comp_fim:
        regime = _regime_juros(comp_atual)

        if regime == "1_pct_mes":
            juros_mes = Decimal("0.01")  # 1% ao mes
        else:
            # SELIC mensal = SELIC anual / 12
            selic_anual = SELIC_ANUAL.get(comp_atual.year, Decimal("12.00"))
            juros_mes = selic_anual / _HUNDRED / _TWELVE

        juros_total += juros_mes

        # Proximo mes
        if comp_atual.month == 12:
            comp_atual = date(comp_atual.year + 1, 1, 1)
        else:
            comp_atual = date(comp_atual.year, comp_atual.month + 1, 1)

    # Juros simples (nao compostos) para todas as faixas — pratica forense
    valor_juros = _q2(valor * juros_total)
    taxa_pct = _q2(juros_total * _HUNDRED)

    return (valor_juros, taxa_pct)


# ---------------------------------------------------------------------------
# Prescricao quinquenal
# ---------------------------------------------------------------------------

def _data_prescricao(data_ajuizamento: Optional[date]) -> Optional[date]:
    """
    Calcula a data limite da prescricao quinquenal.

    Parcelas anteriores a 5 anos antes do ajuizamento da acao estao prescritas.
    Sumula 85/STJ: a prescricao atinge as parcelas, nao o fundo de direito.
    """
    if data_ajuizamento is None:
        return None
    return date(
        data_ajuizamento.year - 5,
        data_ajuizamento.month,
        min(data_ajuizamento.day, 28),  # evita problemas com fev/30/31
    )


# ---------------------------------------------------------------------------
# 13o salario proporcional
# ---------------------------------------------------------------------------

def _calcular_13o_proporcional(
    rmi: Decimal,
    competencias_no_ano: int,
) -> Decimal:
    """
    Calcula o 13o salario proporcional.

    O 13o corresponde a 1/12 do beneficio por mes de recebimento naquele ano.
    """
    if competencias_no_ano <= 0:
        return _ZERO
    return _q2(rmi * Decimal(str(competencias_no_ano)) / _TWELVE)


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def calcular_retroativos(
    rmi_corrigida: Decimal,
    rmi_original: Decimal,
    dib: date,
    dip: Optional[date],
    data_calculo: date,
    data_citacao: Optional[date] = None,
    data_ajuizamento: Optional[date] = None,
    incluir_13o: bool = True,
    abatimentos: Optional[List[Dict]] = None,
) -> ResultadoRetroativos:
    """
    Calcula o total de valores retroativos devidos pelo INSS ao segurado.

    Parametros:
        rmi_corrigida: Renda Mensal Inicial correta (apos revisao/concessao).
        rmi_original: RMI que o INSS pagou (0 se beneficio foi indeferido).
        dib: Data de Inicio do Beneficio (quando DEVERIA ter comecado).
        dip: Data de Inicio do Pagamento (quando o INSS efetivamente pagou).
             None se o beneficio foi totalmente indeferido.
        data_calculo: Data-base do calculo (normalmente hoje).
        data_citacao: Data da citacao do INSS na acao judicial (marco dos juros).
                      Se None, usa data_ajuizamento. Se ambos None, usa a DIB.
        data_ajuizamento: Data do ajuizamento da acao (marco da prescricao).
                          Se None, nao aplica prescricao.
        incluir_13o: Se True, inclui 13o salario proporcional.
        abatimentos: Lista de dicts com 'competencia' (date) e 'valor' (Decimal)
                     para valores ja recebidos que devem ser deduzidos.

    Retorna:
        ResultadoRetroativos com todas as parcelas detalhadas e totais.
    """
    memoria: List[str] = []

    # -----------------------------------------------------------------------
    # 1. Validacoes e normalizacoes
    # -----------------------------------------------------------------------
    if dip is None:
        # Beneficio totalmente indeferido — retroativos vao da DIB ate o calculo
        dip = data_calculo
        memoria.append(
            f"Beneficio indeferido. Retroativos calculados da DIB ({dib.strftime('%d/%m/%Y')}) "
            f"ate a data do calculo ({data_calculo.strftime('%d/%m/%Y')})."
        )
    else:
        memoria.append(
            f"Retroativos calculados da DIB ({dib.strftime('%d/%m/%Y')}) "
            f"ate a DIP ({dip.strftime('%d/%m/%Y')})."
        )

    # Data de citacao: se nao informada, usa ajuizamento; se tb nao, usa DIB
    if data_citacao is None:
        data_citacao = data_ajuizamento if data_ajuizamento else dib
        memoria.append(
            f"Data de citacao nao informada. Usando {data_citacao.strftime('%d/%m/%Y')} "
            f"como marco inicial dos juros de mora."
        )

    # DER = DIB para fins deste calculo (simplificacao; na pratica a DER
    # pode ser anterior, mas os retroativos comecam na DIB)
    der = dib

    memoria.append(f"RMI corrigida (devida): R$ {rmi_corrigida:,.2f}")
    memoria.append(f"RMI original (paga pelo INSS): R$ {rmi_original:,.2f}")
    diferenca_mensal_base = _q2(rmi_corrigida - rmi_original)
    memoria.append(f"Diferenca mensal base: R$ {diferenca_mensal_base:,.2f}")

    # -----------------------------------------------------------------------
    # 2. Prescricao quinquenal
    # -----------------------------------------------------------------------
    limite_prescricao = _data_prescricao(data_ajuizamento)
    if limite_prescricao:
        memoria.append(
            f"Prescricao quinquenal: parcelas anteriores a "
            f"{limite_prescricao.strftime('%d/%m/%Y')} estao prescritas "
            f"(Sumula 85/STJ; Decreto 20.910/32)."
        )
    else:
        memoria.append("Prescricao quinquenal nao aplicada (data de ajuizamento nao informada).")

    # -----------------------------------------------------------------------
    # 3. Montar mapa de abatimentos
    # -----------------------------------------------------------------------
    mapa_abatimentos: Dict[str, Decimal] = {}
    total_abatimento = _ZERO
    if abatimentos:
        for ab in abatimentos:
            comp = ab.get("competencia")
            val = Decimal(str(ab.get("valor", "0")))
            if isinstance(comp, date):
                chave = f"{comp.year}-{comp.month:02d}"
                mapa_abatimentos[chave] = mapa_abatimentos.get(chave, _ZERO) + val
                total_abatimento += val
        if total_abatimento > _ZERO:
            memoria.append(f"Total de abatimentos (valores ja recebidos): R$ {total_abatimento:,.2f}")

    # -----------------------------------------------------------------------
    # 4. Gerar competencias do periodo retroativo
    # -----------------------------------------------------------------------
    # O periodo retroativo vai da DIB ate:
    #   - DIP (se houve concessao tardia ou revisao com pagamento posterior)
    #   - data_calculo (se beneficio foi totalmente indeferido)
    fim_retroativo = dip if dip < data_calculo else data_calculo
    competencias = _gerar_competencias(dib, fim_retroativo)

    memoria.append(f"Periodo: {len(competencias)} competencias de "
                   f"{dib.strftime('%m/%Y')} a {fim_retroativo.strftime('%m/%Y')}.")

    # -----------------------------------------------------------------------
    # 5. Calcular parcela a parcela
    # -----------------------------------------------------------------------
    parcelas: List[ParcelaRetroativa] = []
    total_bruto = _ZERO
    total_corrigido = _ZERO
    total_juros = _ZERO
    parcelas_prescritas = 0
    valor_prescrito = _ZERO
    valor_13os = _ZERO

    # Controle de 13o: contar meses por ano
    meses_por_ano: Dict[int, int] = {}

    for comp in competencias:
        # --- Aplicar teto e piso a RMI ---
        rmi_devida_mes = _aplicar_teto_e_piso(rmi_corrigida, comp)
        rmi_paga_mes = _aplicar_teto_e_piso(rmi_original, comp) if rmi_original > _ZERO else _ZERO

        diferenca = _q2(rmi_devida_mes - rmi_paga_mes)

        # Descontar abatimento especifico do mes, se houver
        chave_comp = f"{comp.year}-{comp.month:02d}"
        if chave_comp in mapa_abatimentos:
            abat_mes = mapa_abatimentos[chave_comp]
            diferenca = _q2(diferenca - abat_mes)
            if diferenca < _ZERO:
                diferenca = _ZERO

        # --- Verificar prescricao ---
        prescrita = False
        if limite_prescricao and comp < limite_prescricao:
            prescrita = True

        # --- Correcao monetaria ---
        valor_corrigido_val, indice_acum = calcular_correcao_monetaria(
            diferenca, comp, data_calculo
        )
        correcao_val = _q2(valor_corrigido_val - diferenca)

        # --- Juros de mora ---
        valor_juros_val, taxa_juros_pct = calcular_juros_mora(
            valor_corrigido_val, data_citacao, data_calculo
        )

        regime = _regime_juros(comp)
        desc_regime = _descricao_regime_juros(regime)

        # --- Montar parcela ---
        parcela = ParcelaRetroativa(
            competencia=comp,
            rmi_devida=rmi_devida_mes,
            rmi_paga=rmi_paga_mes,
            diferenca_bruta=diferenca,
            correcao_monetaria=correcao_val,
            juros_mora=valor_juros_val,
            valor_corrigido=valor_corrigido_val,
            valor_com_juros=_q2(valor_corrigido_val + valor_juros_val),
            indice_correcao=f"INPC (indice acumulado: {indice_acum})",
            taxa_juros=f"{desc_regime} ({taxa_juros_pct}%)",
            prescrita=prescrita,
        )
        parcelas.append(parcela)

        # --- Acumular totais (apenas parcelas nao prescritas) ---
        if prescrita:
            parcelas_prescritas += 1
            valor_prescrito += _q2(valor_corrigido_val + valor_juros_val)
        else:
            total_bruto += diferenca
            total_corrigido += valor_corrigido_val
            total_juros += valor_juros_val

        # Contar meses para 13o
        meses_por_ano[comp.year] = meses_por_ano.get(comp.year, 0) + 1

    # -----------------------------------------------------------------------
    # 6. Calcular 13o salario proporcional
    # -----------------------------------------------------------------------
    if incluir_13o:
        memoria.append("--- 13o SALARIO PROPORCIONAL ---")
        for ano, qtd_meses in sorted(meses_por_ano.items()):
            # Verificar se o ano inteiro esta prescrito
            comp_dez = date(ano, 12, 1)
            if limite_prescricao and comp_dez < limite_prescricao:
                memoria.append(
                    f"  13o de {ano}: prescrito ({qtd_meses} meses)."
                )
                continue

            rmi_13_devida = _aplicar_teto_e_piso(rmi_corrigida, date(ano, 12, 1))
            rmi_13_paga = (
                _aplicar_teto_e_piso(rmi_original, date(ano, 12, 1))
                if rmi_original > _ZERO else _ZERO
            )

            valor_13_devido = _calcular_13o_proporcional(rmi_13_devida, qtd_meses)
            valor_13_pago = _calcular_13o_proporcional(rmi_13_paga, qtd_meses)
            dif_13 = _q2(valor_13_devido - valor_13_pago)

            if dif_13 > _ZERO:
                # Corrigir e aplicar juros
                data_ref_13 = date(ano, 12, 1)
                v13_corrigido, idx_13 = calcular_correcao_monetaria(
                    dif_13, data_ref_13, data_calculo
                )
                j13, tx13 = calcular_juros_mora(v13_corrigido, data_citacao, data_calculo)

                valor_13os += _q2(v13_corrigido + j13)
                total_bruto += dif_13
                total_corrigido += v13_corrigido
                total_juros += j13

                memoria.append(
                    f"  13o de {ano}: {qtd_meses}/12 avos = R$ {dif_13:,.2f} "
                    f"-> corrigido R$ {v13_corrigido:,.2f} + juros R$ {j13:,.2f}"
                )
    else:
        memoria.append("13o salario proporcional NAO incluido (parametro desativado).")

    # -----------------------------------------------------------------------
    # 7. Consolidar totais
    # -----------------------------------------------------------------------
    total_bruto = _q2(total_bruto)
    total_corrigido = _q2(total_corrigido)
    total_juros = _q2(total_juros)
    valor_prescrito = _q2(valor_prescrito)
    valor_13os = _q2(valor_13os)
    total_abatimento = _q2(total_abatimento)

    total_liquido = _q2(total_corrigido + total_juros - total_abatimento)
    if total_liquido < _ZERO:
        total_liquido = _ZERO

    memoria.append("")
    memoria.append("=" * 60)
    memoria.append("RESUMO DO CALCULO DE RETROATIVOS")
    memoria.append("=" * 60)
    memoria.append(f"DIB: {dib.strftime('%d/%m/%Y')}")
    memoria.append(f"DIP: {dip.strftime('%d/%m/%Y')}")
    memoria.append(f"Data do calculo: {data_calculo.strftime('%d/%m/%Y')}")
    memoria.append(f"RMI corrigida: R$ {rmi_corrigida:,.2f}")
    memoria.append(f"RMI original: R$ {rmi_original:,.2f}")
    memoria.append(f"Total de parcelas: {len(parcelas)}")
    memoria.append(f"Parcelas prescritas: {parcelas_prescritas}")
    memoria.append(f"Valor prescrito (nao cobravel): R$ {valor_prescrito:,.2f}")
    memoria.append(f"Total bruto (diferencas): R$ {total_bruto:,.2f}")
    memoria.append(f"Total corrigido (INPC): R$ {total_corrigido:,.2f}")
    memoria.append(f"Total juros de mora: R$ {total_juros:,.2f}")
    memoria.append(f"Valor dos 13os: R$ {valor_13os:,.2f}")
    memoria.append(f"Abatimento: R$ {total_abatimento:,.2f}")
    memoria.append(f"TOTAL LIQUIDO: R$ {total_liquido:,.2f}")
    memoria.append("=" * 60)

    # -----------------------------------------------------------------------
    # 8. Disclaimer
    # -----------------------------------------------------------------------
    disclaimer = (
        "AVISO: Este calculo utiliza indices simplificados (INPC e SELIC anuais "
        "rateados mensalmente). Para peticao judicial, recomenda-se a conferencia "
        "com indices oficiais do IBGE e do Banco Central, utilizando calculadora "
        "da Justica Federal ou planilha pericial. Os valores aqui apresentados "
        "servem como estimativa fundamentada e memoria de calculo auditavel, "
        "nao substituindo laudo pericial contabil."
    )
    memoria.append("")
    memoria.append(disclaimer)

    return ResultadoRetroativos(
        dib=dib,
        dip=dip,
        der=der,
        data_calculo=data_calculo,
        rmi_original=rmi_original,
        rmi_corrigida=rmi_corrigida,
        diferenca_mensal=diferenca_mensal_base,
        total_bruto=total_bruto,
        total_corrigido=total_corrigido,
        total_juros=total_juros,
        total_liquido=total_liquido,
        abatimento=total_abatimento,
        parcelas=parcelas,
        parcelas_prescritas=parcelas_prescritas,
        valor_prescrito=valor_prescrito,
        valor_13os=valor_13os,
        memoria_calculo=memoria,
        disclaimer=disclaimer,
    )
