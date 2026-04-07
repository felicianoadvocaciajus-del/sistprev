"""
Motor de acordos internacionais de previdencia social.

Implementa a logica de totalizacao de tempo de contribuicao entre o Brasil
e paises signatarios de acordos bilaterais/multilaterais, conforme a
legislacao vigente e os tratados internacionais ratificados.

CONCEITOS FUNDAMENTAIS:
1. TOTALIZACAO (Art. 34 do Decreto 3.048/99 c/c cada acordo):
   Soma do tempo de contribuicao no Brasil e no exterior para atingir
   os requisitos minimos de elegibilidade (carencia e tempo).
   IMPORTANTE: A totalizacao serve APENAS para verificar elegibilidade.
   O calculo do valor segue a regra de proporcionalidade (pro-rata).

2. PROPORCIONALIDADE (PRO-RATA TEMPORIS):
   Cada pais paga o beneficio na proporcao do tempo contribuido em seu
   territorio. Ex: 20 anos no Brasil + 10 anos na Espanha = Brasil paga
   2/3 do beneficio calculado sobre suas proprias regras.

3. EXPORTACAO DE BENEFICIO:
   O beneficio concedido por totalizacao pode ser pago no exterior,
   conforme Art. 181 do Decreto 3.048/99 e cada acordo especifico.

4. DUPLA COBERTURA:
   Trabalhador deslocado temporariamente (ate 24 ou 60 meses conforme
   acordo) continua vinculado apenas ao regime de origem.

LEGISLACAO BASE:
- Decreto 3.048/99, Art. 34 e ss. (Regulamento da Previdencia Social)
- Lei 8.213/91, Art. 40 (Acordos internacionais)
- Cada decreto de promulgacao do acordo bilateral/multilateral
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.segurado import Segurado


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class AcordoInternacional:
    """Representa um acordo bilateral ou multilateral de previdencia social."""

    pais: str
    decreto: str
    vigencia: date
    tipo: str  # "bilateral" ou "multilateral"
    permite_totalizacao: bool = True
    permite_exportacao: bool = True
    formulario_ligacao: str = ""
    observacoes: str = ""
    prazo_deslocamento_meses: int = 24  # dupla cobertura
    orgao_estrangeiro: str = ""  # nome do orgao previdenciario no pais


@dataclass
class PeriodoExterior:
    """Periodo de contribuicao cumprido no exterior sob acordo internacional."""

    pais: str
    data_inicio: date
    data_fim: Optional[date]
    dias_contribuicao: int
    orgao_previdenciario: str  # ex: "Seguridad Social - Espana"
    comprovante: str  # tipo de documento comprobatorio

    def __post_init__(self) -> None:
        if self.dias_contribuicao < 0:
            raise ValueError(
                f"dias_contribuicao nao pode ser negativo: {self.dias_contribuicao}"
            )
        if self.data_fim is not None and self.data_fim < self.data_inicio:
            raise ValueError(
                f"data_fim ({self.data_fim}) anterior a data_inicio ({self.data_inicio})"
            )


@dataclass
class ResultadoTotalizacao:
    """Resultado completo do calculo de totalizacao internacional."""

    tc_brasil_dias: int
    tc_exterior_dias: int
    tc_total_dias: int
    elegivel_com_totalizacao: bool
    elegivel_sem_totalizacao: bool
    rmi_proporcional: Decimal  # valor proporcional ao tempo no Brasil
    rmi_integral: Decimal  # valor hipotetico se todo o tempo fosse no Brasil
    pro_rata: Decimal  # fracao (ex: 0.65 = 65% do tempo no Brasil)
    acordo: AcordoInternacional
    memoria: List[str] = field(default_factory=list)
    documentos_necessarios: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BASE DE ACORDOS INTERNACIONAIS
# Dados estaticos conforme legislacao vigente. Atualizado em 2025-12.
# ---------------------------------------------------------------------------

_ACORDOS: Dict[str, AcordoInternacional] = {}


def _registrar(chave: str, acordo: AcordoInternacional) -> None:
    """Registra um acordo na base interna."""
    _ACORDOS[chave.upper()] = acordo


# -- Espanha ---------------------------------------------------------------
_registrar("ESPANHA", AcordoInternacional(
    pais="Espanha",
    decreto="Decreto 1.689/1995",
    vigencia=date(1995, 10, 6),
    tipo="bilateral",
    formulario_ligacao="ESP-BRA/1 a ESP-BRA/10",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Instituto Nacional de la Seguridad Social (INSS Espana)",
    observacoes=(
        "Acordo de Seguridade Social entre Brasil e Espanha. "
        "Permite totalizacao para aposentadoria por idade, invalidez "
        "e pensao por morte. Formularios de ligacao ESP-BRA numerados de 1 a 10."
    ),
))

# -- Portugal ---------------------------------------------------------------
_registrar("PORTUGAL", AcordoInternacional(
    pais="Portugal",
    decreto="Decreto 7.999/2013",
    vigencia=date(2013, 5, 2),
    tipo="bilateral",
    formulario_ligacao="PRT-BRA/1 a PRT-BRA/8",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Instituto da Seguranca Social (ISS)",
    observacoes=(
        "Acordo entre Brasil e Portugal, substitui o acordo de 1995. "
        "Abrange aposentadorias, pensao por morte e auxilio-doenca. "
        "Inclui trabalhadores autonomos."
    ),
))

# -- Italia ----------------------------------------------------------------
_registrar("ITALIA", AcordoInternacional(
    pais="Italia",
    decreto="Decreto 1.575/1995",
    vigencia=date(1995, 10, 5),
    tipo="bilateral",
    formulario_ligacao="ITA-BRA/1 a ITA-BRA/9",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Istituto Nazionale della Previdenza Sociale (INPS Italia)",
    observacoes=(
        "Acordo de Previdencia Social entre Brasil e Italia. "
        "Abrange aposentadoria por idade, invalidez, pensao por morte. "
        "Formularios de ligacao ITA-BRA numerados de 1 a 9."
    ),
))

# -- Japao -----------------------------------------------------------------
_registrar("JAPAO", AcordoInternacional(
    pais="Japao",
    decreto="Decreto 10.260/2020",
    vigencia=date(2020, 3, 2),
    tipo="bilateral",
    formulario_ligacao="JPN-BRA/1 a JPN-BRA/6",
    prazo_deslocamento_meses=60,
    orgao_estrangeiro="Japan Pension Service (JPS)",
    observacoes=(
        "Acordo entre Brasil e Japao. Deslocamento temporario de ate 60 meses. "
        "Abrange o National Pension (Kokumin Nenkin) e Employees' Pension "
        "(Kosei Nenkin). Importante para comunidade nipo-brasileira."
    ),
))

# -- Alemanha ---------------------------------------------------------------
_registrar("ALEMANHA", AcordoInternacional(
    pais="Alemanha",
    decreto="Decreto 5.765/2006",
    vigencia=date(2006, 6, 20),
    tipo="bilateral",
    formulario_ligacao="DEU-BRA/1 a DEU-BRA/8",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Deutsche Rentenversicherung (DRV)",
    observacoes=(
        "Acordo de Previdencia Social entre Brasil e Alemanha. "
        "Abrange aposentadoria por idade, invalidez e pensao por morte. "
        "Permite extensao do deslocamento por mais 24 meses com autorizacao."
    ),
))

# -- Franca ----------------------------------------------------------------
_registrar("FRANCA", AcordoInternacional(
    pais="Franca",
    decreto="Decreto 3.598/2000",
    vigencia=date(2000, 9, 1),
    tipo="bilateral",
    formulario_ligacao="FRA-BRA/1 a FRA-BRA/8",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Caisse Nationale d'Assurance Vieillesse (CNAV)",
    observacoes=(
        "Convenio de Previdencia Social entre Brasil e Franca. "
        "Abrange regime geral de ambos os paises. Formularios "
        "de ligacao FRA-BRA numerados de 1 a 8."
    ),
))

# -- Estados Unidos ---------------------------------------------------------
_registrar("EUA", AcordoInternacional(
    pais="Estados Unidos",
    decreto="Decreto 9.422/2018",
    vigencia=date(2018, 10, 1),
    tipo="bilateral",
    formulario_ligacao="USA-BRA/1 a USA-BRA/6",
    prazo_deslocamento_meses=60,
    orgao_estrangeiro="Social Security Administration (SSA)",
    observacoes=(
        "Acordo de Previdencia Social entre Brasil e EUA. "
        "Deslocamento temporario de ate 60 meses. Abrange aposentadoria "
        "por idade e pensao por morte (Title II do Social Security Act). "
        "NAO abrange Medicare nem programas estaduais."
    ),
))
_registrar("ESTADOS UNIDOS", _ACORDOS["EUA"])

# -- MERCOSUL (Multilateral) -----------------------------------------------
_registrar("MERCOSUL", AcordoInternacional(
    pais="MERCOSUL (Argentina, Paraguai, Uruguai)",
    decreto="Decreto 5.722/2006",
    vigencia=date(2006, 6, 20),
    tipo="multilateral",
    formulario_ligacao="MERCOSUL/1 a MERCOSUL/8",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Organismo de ligacao de cada Estado-Parte",
    observacoes=(
        "Acordo Multilateral de Seguridade Social do MERCOSUL. "
        "Abrange Brasil, Argentina, Paraguai e Uruguai. "
        "A totalizacao soma periodos em qualquer dos Estados-Parte. "
        "Venezuela ratificou mas esta suspensa do MERCOSUL."
    ),
))
# Aliases para paises do MERCOSUL
for _alias_merc in ("ARGENTINA", "PARAGUAI", "URUGUAI"):
    _registrar(_alias_merc, _ACORDOS["MERCOSUL"])

# -- Ibero-Americana (Multilateral) ----------------------------------------
_registrar("IBEROAMERICANA", AcordoInternacional(
    pais="Convencao Multilateral Ibero-Americana",
    decreto="Decreto 8.358/2014",
    vigencia=date(2014, 12, 10),
    tipo="multilateral",
    formulario_ligacao="CMISS/1 a CMISS/5",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Organismo de ligacao de cada Estado-Parte",
    observacoes=(
        "Convencao Multilateral Ibero-Americana de Seguridade Social (CMISS). "
        "Abrange: Espanha, Portugal, Brasil, Argentina, Boliva, Chile, "
        "Colômbia, Costa Rica, El Salvador, Equador, Paraguai, Peru, Uruguai "
        "e Venezuela. Complementa (nao substitui) acordos bilaterais existentes."
    ),
))

# Paises adicionais cobertos pela Ibero-Americana sem acordo bilateral proprio
for _alias_ibero in ("CHILE", "COLOMBIA", "PERU", "EQUADOR", "BOLIVIA",
                      "COSTA RICA", "EL SALVADOR"):
    _registrar(_alias_ibero, _ACORDOS["IBEROAMERICANA"])

# -- Outros acordos bilaterais menores (cabo verde, grecia, etc.) -----------
_registrar("CABO VERDE", AcordoInternacional(
    pais="Cabo Verde",
    decreto="Decreto 5.765/2006",
    vigencia=date(2006, 6, 20),
    tipo="bilateral",
    formulario_ligacao="CPV-BRA/1 a CPV-BRA/6",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Instituto Nacional de Previdencia Social (INPS Cabo Verde)",
    observacoes="Acordo bilateral Brasil-Cabo Verde.",
))

_registrar("GRECIA", AcordoInternacional(
    pais="Grecia",
    decreto="Decreto 1.681/1995",
    vigencia=date(1995, 10, 5),
    tipo="bilateral",
    formulario_ligacao="GRC-BRA/1 a GRC-BRA/6",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="IKA-ETAM (Grecia)",
    observacoes="Acordo bilateral Brasil-Grecia.",
))

_registrar("BELGICA", AcordoInternacional(
    pais="Belgica",
    decreto="Decreto 6.927/2009",
    vigencia=date(2009, 8, 12),
    tipo="bilateral",
    formulario_ligacao="BEL-BRA/1 a BEL-BRA/6",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Office National des Pensions (ONP)",
    observacoes="Acordo bilateral Brasil-Belgica.",
))

_registrar("CANADA", AcordoInternacional(
    pais="Canada",
    decreto="Decreto 8.288/2014",
    vigencia=date(2014, 8, 1),
    tipo="bilateral",
    formulario_ligacao="CAN-BRA/1 a CAN-BRA/6",
    prazo_deslocamento_meses=60,
    orgao_estrangeiro="Service Canada",
    observacoes=(
        "Acordo bilateral Brasil-Canada. Deslocamento de ate 60 meses. "
        "Abrange Canada Pension Plan (CPP) e Old Age Security (OAS)."
    ),
))

_registrar("COREIA DO SUL", AcordoInternacional(
    pais="Coreia do Sul",
    decreto="Decreto 10.286/2020",
    vigencia=date(2020, 11, 1),
    tipo="bilateral",
    formulario_ligacao="KOR-BRA/1 a KOR-BRA/6",
    prazo_deslocamento_meses=60,
    orgao_estrangeiro="National Pension Service (NPS)",
    observacoes="Acordo bilateral Brasil-Coreia do Sul.",
))

_registrar("ISRAEL", AcordoInternacional(
    pais="Israel",
    decreto="Decreto 11.435/2023",
    vigencia=date(2023, 3, 17),
    tipo="bilateral",
    formulario_ligacao="ISR-BRA/1 a ISR-BRA/6",
    prazo_deslocamento_meses=60,
    orgao_estrangeiro="National Insurance Institute (Bituach Leumi)",
    observacoes="Acordo bilateral Brasil-Israel. Mais recente acordo vigente.",
))

_registrar("SUICA", AcordoInternacional(
    pais="Suica",
    decreto="Decreto 11.199/2022",
    vigencia=date(2022, 9, 1),
    tipo="bilateral",
    formulario_ligacao="CHE-BRA/1 a CHE-BRA/6",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Ausgleichskasse / AVS",
    observacoes="Acordo bilateral Brasil-Suica.",
))

_registrar("LUXEMBURGO", AcordoInternacional(
    pais="Luxemburgo",
    decreto="Decreto 5.765/2006",
    vigencia=date(2006, 6, 20),
    tipo="bilateral",
    formulario_ligacao="LUX-BRA/1 a LUX-BRA/6",
    prazo_deslocamento_meses=24,
    orgao_estrangeiro="Caisse Nationale d'Assurance Pension (CNAP)",
    observacoes="Acordo bilateral Brasil-Luxemburgo.",
))


# ---------------------------------------------------------------------------
# FUNCOES PUBLICAS
# ---------------------------------------------------------------------------

def listar_acordos() -> Dict[str, AcordoInternacional]:
    """Retorna copia do dicionario de todos os acordos registrados.

    Returns:
        Dicionario com chave normalizada (pais em maiusculas) e o acordo.
    """
    return dict(_ACORDOS)


def verificar_acordo(pais: str) -> Optional[AcordoInternacional]:
    """Verifica se existe acordo previdenciario com o pais informado.

    Busca pelo nome do pais (case-insensitive), tentando variantes comuns.

    Args:
        pais: Nome do pais (ex: "Espanha", "espanha", "EUA", "estados unidos").

    Returns:
        O AcordoInternacional encontrado, ou None se nao houver acordo.

    Example:
        >>> acordo = verificar_acordo("Espanha")
        >>> acordo.decreto
        'Decreto 1.689/1995'
    """
    normalizado = pais.strip().upper()

    # Busca direta
    if normalizado in _ACORDOS:
        return _ACORDOS[normalizado]

    # Tenta variantes comuns
    _ALIASES: Dict[str, str] = {
        "SPAIN": "ESPANHA",
        "PORTUGAL": "PORTUGAL",
        "ITALY": "ITALIA",
        "JAPAN": "JAPAO",
        "GERMANY": "ALEMANHA",
        "FRANCE": "FRANCA",
        "USA": "EUA",
        "UNITED STATES": "EUA",
        "ESTADOS UNIDOS DA AMERICA": "EUA",
        "ESTADOS UNIDOS": "EUA",
        "SOUTH KOREA": "COREIA DO SUL",
        "SWITZERLAND": "SUICA",
        "BELGIUM": "BELGICA",
        "GREECE": "GRECIA",
        "CAPE VERDE": "CABO VERDE",
        "LUXEMBOURG": "LUXEMBURGO",
        "CANADA": "CANADA",
        "ISRAEL": "ISRAEL",
        "MERCOSUR": "MERCOSUL",
        "ARGENTINA": "ARGENTINA",
        "PARAGUAY": "PARAGUAI",
        "URUGUAY": "URUGUAI",
        "IBERO-AMERICANA": "IBEROAMERICANA",
        "IBEROAMERICANA": "IBEROAMERICANA",
    }

    if normalizado in _ALIASES:
        chave = _ALIASES[normalizado]
        return _ACORDOS.get(chave)

    # Busca parcial (substring)
    for chave, acordo in _ACORDOS.items():
        if normalizado in chave or chave in normalizado:
            return acordo
        if normalizado in acordo.pais.upper():
            return acordo

    return None


def calcular_totalizacao(
    segurado: "Segurado",
    der: date,
    periodos_exterior: List[PeriodoExterior],
) -> ResultadoTotalizacao:
    """Calcula a totalizacao de tempo de contribuicao com periodos no exterior.

    Implementa o calculo conforme as regras de totalizacao e proporcionalidade
    (pro-rata temporis) previstas nos acordos internacionais.

    LOGICA:
    1. Soma o tempo de contribuicao no Brasil (vinculos do segurado).
    2. Soma os periodos no exterior (informados via formularios de ligacao).
    3. Verifica elegibilidade com e sem totalizacao.
    4. Calcula a proporcao (pro-rata) do Brasil sobre o total.
    5. Aplica a proporcao sobre a RMI integral para obter a RMI proporcional.

    Args:
        segurado: Dados completos do segurado (vinculos, contribuicoes, etc.).
        der: Data de Entrada do Requerimento.
        periodos_exterior: Lista de periodos contribuidos no exterior.

    Returns:
        ResultadoTotalizacao com todos os dados do calculo.

    Raises:
        ValueError: Se nao houver acordo com algum dos paises informados.
    """
    memoria: List[str] = []
    memoria.append("=" * 60)
    memoria.append("CALCULO DE TOTALIZACAO INTERNACIONAL")
    memoria.append(f"DER: {der.strftime('%d/%m/%Y')}")
    memoria.append(f"Segurado: {segurado.dados_pessoais.nome}")
    memoria.append("=" * 60)

    # -----------------------------------------------------------------------
    # 1. TEMPO DE CONTRIBUICAO NO BRASIL
    # -----------------------------------------------------------------------
    tc_brasil_dias = _calcular_tc_brasil(segurado, der, memoria)

    # -----------------------------------------------------------------------
    # 2. TEMPO NO EXTERIOR
    # -----------------------------------------------------------------------
    tc_exterior_dias = 0
    acordo_principal: Optional[AcordoInternacional] = None

    for periodo in periodos_exterior:
        acordo = verificar_acordo(periodo.pais)
        if acordo is None:
            raise ValueError(
                f"Nao ha acordo previdenciario vigente com '{periodo.pais}'. "
                f"Sem acordo, nao e possivel totalizar o tempo no exterior."
            )

        if acordo_principal is None:
            acordo_principal = acordo

        dias = periodo.dias_contribuicao
        if dias == 0 and periodo.data_fim is not None:
            # Calcula dias pelo periodo se nao informado explicitamente
            dias = (periodo.data_fim - periodo.data_inicio).days + 1

        tc_exterior_dias += dias

        memoria.append("")
        memoria.append(f"Periodo no exterior - {periodo.pais}:")
        memoria.append(f"  Acordo: {acordo.decreto}")
        memoria.append(f"  Orgao: {periodo.orgao_previdenciario}")
        memoria.append(
            f"  Periodo: {periodo.data_inicio.strftime('%d/%m/%Y')} a "
            f"{periodo.data_fim.strftime('%d/%m/%Y') if periodo.data_fim else 'atual'}"
        )
        memoria.append(f"  Dias de contribuicao: {dias}")
        memoria.append(f"  Comprovante: {periodo.comprovante}")

    # Fallback se nenhum periodo foi informado (nao deveria ocorrer)
    if acordo_principal is None:
        raise ValueError("Nenhum periodo no exterior informado para totalizacao.")

    # -----------------------------------------------------------------------
    # 3. TOTALIZACAO
    # -----------------------------------------------------------------------
    tc_total_dias = tc_brasil_dias + tc_exterior_dias

    memoria.append("")
    memoria.append("-" * 60)
    memoria.append("RESUMO DA TOTALIZACAO:")
    memoria.append(f"  Tempo no Brasil:  {tc_brasil_dias} dias "
                   f"({_dias_para_anos_meses(tc_brasil_dias)})")
    memoria.append(f"  Tempo no exterior: {tc_exterior_dias} dias "
                   f"({_dias_para_anos_meses(tc_exterior_dias)})")
    memoria.append(f"  Tempo TOTAL:       {tc_total_dias} dias "
                   f"({_dias_para_anos_meses(tc_total_dias)})")
    memoria.append("-" * 60)

    # -----------------------------------------------------------------------
    # 4. VERIFICACAO DE ELEGIBILIDADE
    # -----------------------------------------------------------------------
    from ..enums import Sexo

    sexo = segurado.sexo
    idade = segurado.idade_na(der)

    # Requisitos pos-reforma EC 103/2019 (regra permanente)
    # Aposentadoria por idade:
    #   Homem: 65 anos + 20 anos TC (7.300 dias) / 180 meses carencia
    #   Mulher: 62 anos + 15 anos TC (5.475 dias) / 180 meses carencia
    if sexo == Sexo.MASCULINO:
        idade_minima = Decimal("65")
        tc_minimo_dias = 7300  # 20 anos * 365
    else:
        idade_minima = Decimal("62")
        tc_minimo_dias = 5475  # 15 anos * 365

    cumpre_idade = idade >= idade_minima
    elegivel_sem_totalizacao = cumpre_idade and tc_brasil_dias >= tc_minimo_dias
    elegivel_com_totalizacao = cumpre_idade and tc_total_dias >= tc_minimo_dias

    memoria.append("")
    memoria.append("VERIFICACAO DE ELEGIBILIDADE (Aposentadoria por Idade):")
    memoria.append(f"  Sexo: {'Masculino' if sexo == Sexo.MASCULINO else 'Feminino'}")
    memoria.append(f"  Idade na DER: {idade:.2f} anos")
    memoria.append(f"  Idade minima: {idade_minima} anos -> "
                   f"{'CUMPRE' if cumpre_idade else 'NAO CUMPRE'}")
    memoria.append(f"  TC minimo: {tc_minimo_dias} dias "
                   f"({_dias_para_anos_meses(tc_minimo_dias)})")
    memoria.append(f"  Elegivel SEM totalizacao: "
                   f"{'SIM' if elegivel_sem_totalizacao else 'NAO'}")
    memoria.append(f"  Elegivel COM totalizacao: "
                   f"{'SIM' if elegivel_com_totalizacao else 'NAO'}")

    # -----------------------------------------------------------------------
    # 5. CALCULO PRO-RATA
    # -----------------------------------------------------------------------
    if tc_total_dias > 0:
        pro_rata = (
            Decimal(str(tc_brasil_dias)) / Decimal(str(tc_total_dias))
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        pro_rata = Decimal("0")

    # RMI integral hipotetica: calculo como se todo o tempo fosse no Brasil.
    # Usamos a regra simplificada pos-EC 103/2019:
    #   60% + 2% por ano acima de 20 anos (H) ou 15 anos (M) sobre a media
    #   dos salarios de contribuicao.
    rmi_integral = _calcular_rmi_hipotetica(segurado, der, tc_total_dias, memoria)

    # RMI proporcional: aplica o pro-rata sobre a integral
    rmi_proporcional = (rmi_integral * pro_rata).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    memoria.append("")
    memoria.append("CALCULO DO VALOR (PRO-RATA TEMPORIS):")
    memoria.append(f"  Pro-rata Brasil: {pro_rata:.6f} "
                   f"({float(pro_rata) * 100:.2f}%)")
    memoria.append(f"  RMI integral (hipotetica): R$ {rmi_integral:,.2f}")
    memoria.append(f"  RMI proporcional Brasil:   R$ {rmi_proporcional:,.2f}")

    if not elegivel_com_totalizacao:
        memoria.append("")
        memoria.append("ATENCAO: Segurado NAO atinge os requisitos mesmo com "
                       "totalizacao. Verificar outras regras de transicao ou "
                       "possibilidade de complementacao de contribuicoes.")

    # -----------------------------------------------------------------------
    # 6. DOCUMENTOS NECESSARIOS
    # -----------------------------------------------------------------------
    docs = _listar_documentos_necessarios(acordo_principal, periodos_exterior)
    docs_str = [d["documento"] for d in docs]

    memoria.append("")
    memoria.append("DOCUMENTOS NECESSARIOS:")
    for i, doc in enumerate(docs, 1):
        memoria.append(f"  {i}. {doc['documento']}")
        if doc.get("observacao"):
            memoria.append(f"     -> {doc['observacao']}")

    return ResultadoTotalizacao(
        tc_brasil_dias=tc_brasil_dias,
        tc_exterior_dias=tc_exterior_dias,
        tc_total_dias=tc_total_dias,
        elegivel_com_totalizacao=elegivel_com_totalizacao,
        elegivel_sem_totalizacao=elegivel_sem_totalizacao,
        rmi_proporcional=rmi_proporcional,
        rmi_integral=rmi_integral,
        pro_rata=pro_rata,
        acordo=acordo_principal,
        memoria=memoria,
        documentos_necessarios=docs_str,
    )


def documentos_necessarios(pais: str) -> List[Dict[str, str]]:
    """Lista os documentos necessarios para instruir processo de acordo internacional.

    Args:
        pais: Nome do pais do acordo.

    Returns:
        Lista de dicionarios com 'documento' e 'observacao'.

    Raises:
        ValueError: Se nao houver acordo com o pais informado.
    """
    acordo = verificar_acordo(pais)
    if acordo is None:
        raise ValueError(f"Nao ha acordo previdenciario vigente com '{pais}'.")

    return _listar_documentos_necessarios(acordo, [])


# ---------------------------------------------------------------------------
# FUNCOES INTERNAS
# ---------------------------------------------------------------------------

def _calcular_tc_brasil(
    segurado: "Segurado",
    der: date,
    memoria: List[str],
) -> int:
    """Calcula o tempo de contribuicao no Brasil em dias.

    Soma os periodos de todos os vinculos do segurado, limitando a data_fim
    pela DER (nao conta tempo posterior ao requerimento).
    """
    total_dias = 0

    memoria.append("")
    memoria.append("TEMPO DE CONTRIBUICAO NO BRASIL:")

    for vinculo in segurado.vinculos:
        inicio = vinculo.data_inicio
        fim = vinculo.data_fim if vinculo.data_fim else der

        # Limita pela DER
        if fim > der:
            fim = der

        if fim < inicio:
            continue

        dias = (fim - inicio).days + 1  # Inclusive ambas as datas
        total_dias += dias

        memoria.append(
            f"  Vinculo: {inicio.strftime('%d/%m/%Y')} a "
            f"{fim.strftime('%d/%m/%Y')} = {dias} dias"
        )

    memoria.append(f"  TOTAL BRASIL: {total_dias} dias "
                   f"({_dias_para_anos_meses(total_dias)})")

    return total_dias


def _calcular_rmi_hipotetica(
    segurado: "Segurado",
    der: date,
    tc_total_dias: int,
    memoria: List[str],
) -> Decimal:
    """Calcula a RMI hipotetica como se todo o tempo fosse no Brasil.

    Utiliza a regra pos-EC 103/2019 (Art. 26):
    - Media de TODOS os salarios de contribuicao desde 07/1994
    - Coeficiente: 60% + 2% por ano acima de 20 anos (H) ou 15 anos (M)

    Se nao houver contribuicoes suficientes para calcular a media,
    utiliza o salario minimo como piso.
    """
    from ..enums import Sexo

    SALARIO_MINIMO = Decimal("1518.00")  # Valor vigente 2025

    # Coleta salarios de contribuicao
    contribuicoes = segurado.todas_contribuicoes()
    salarios = [c.salario_contribuicao for c in contribuicoes
                if c.salario_contribuicao and c.salario_contribuicao > Decimal("0")]

    if salarios:
        media = sum(salarios) / len(salarios)
        media = media.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        media = SALARIO_MINIMO

    # Coeficiente EC 103/2019
    tc_anos = tc_total_dias / Decimal("365.25")
    sexo = segurado.sexo
    anos_base = Decimal("20") if sexo == Sexo.MASCULINO else Decimal("15")

    if tc_anos > anos_base:
        excedente = int(tc_anos - anos_base)
        coeficiente = Decimal("0.60") + Decimal("0.02") * Decimal(str(excedente))
    else:
        coeficiente = Decimal("0.60")

    # Teto de 100%
    if coeficiente > Decimal("1.00"):
        coeficiente = Decimal("1.00")

    rmi = (media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Piso do salario minimo
    if rmi < SALARIO_MINIMO:
        rmi = SALARIO_MINIMO

    memoria.append("")
    memoria.append("CALCULO DA RMI HIPOTETICA (EC 103/2019):")
    memoria.append(f"  Media dos salarios: R$ {media:,.2f}")
    memoria.append(f"  TC total para coeficiente: {float(tc_anos):.2f} anos")
    memoria.append(f"  Coeficiente: {float(coeficiente) * 100:.0f}%")
    memoria.append(f"  RMI hipotetica: R$ {rmi:,.2f}")

    return rmi


def _listar_documentos_necessarios(
    acordo: AcordoInternacional,
    periodos_exterior: List[PeriodoExterior],
) -> List[Dict[str, str]]:
    """Monta a lista de documentos necessarios para o processo.

    Retorna documentos universais + especificos do acordo.
    """
    docs: List[Dict[str, str]] = []

    # Documentos universais
    docs.append({
        "documento": "Documento de identidade (RG ou passaporte)",
        "observacao": "Copia autenticada ou digital",
    })
    docs.append({
        "documento": "CPF",
        "observacao": "",
    })
    docs.append({
        "documento": "CTPS (Carteira de Trabalho e Previdencia Social)",
        "observacao": "Todas as paginas com anotacoes de contratos",
    })
    docs.append({
        "documento": "CNIS (Cadastro Nacional de Informacoes Sociais)",
        "observacao": "Extrato atualizado do INSS (meuinss.gov.br)",
    })
    docs.append({
        "documento": "Comprovante de residencia atualizado",
        "observacao": "Endereco no Brasil ou no exterior",
    })

    # Formularios de ligacao do acordo
    if acordo.formulario_ligacao:
        docs.append({
            "documento": f"Formulario(s) de ligacao: {acordo.formulario_ligacao}",
            "observacao": (
                f"Formulario padronizado do acordo {acordo.decreto}. "
                f"Preenchido pelo orgao previdenciario de cada pais."
            ),
        })

    # Documentos especificos do exterior
    docs.append({
        "documento": (
            f"Certidao de tempo de contribuicao no exterior "
            f"emitida pelo {acordo.orgao_estrangeiro}"
        ),
        "observacao": "Documento original ou autenticado pela reparticao consular",
    })
    docs.append({
        "documento": "Traducao juramentada de documentos em idioma estrangeiro",
        "observacao": "Exigida para todos os documentos nao redigidos em portugues",
    })

    # Se ha deslocamento temporario
    for periodo in periodos_exterior:
        if periodo.comprovante:
            docs.append({
                "documento": f"Comprovante de contribuicao: {periodo.comprovante}",
                "observacao": f"Referente ao periodo em {periodo.pais}",
            })

    # Documentos de processo
    docs.append({
        "documento": "Procuracao (se representado por advogado)",
        "observacao": "Com poderes especificos para requerer beneficio via acordo internacional",
    })
    docs.append({
        "documento": "Requerimento administrativo ao INSS (formulario especifico)",
        "observacao": (
            "Agendar atendimento na Agencia da Previdencia Social especializada "
            "em acordos internacionais"
        ),
    })

    return docs


def _dias_para_anos_meses(dias: int) -> str:
    """Converte dias em string legivel 'X anos, Y meses e Z dias'."""
    if dias <= 0:
        return "0 dias"

    anos = dias // 365
    resto = dias % 365
    meses = resto // 30
    dias_resto = resto % 30

    partes: List[str] = []
    if anos > 0:
        partes.append(f"{anos} ano{'s' if anos != 1 else ''}")
    if meses > 0:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if dias_resto > 0 or not partes:
        partes.append(f"{dias_resto} dia{'s' if dias_resto != 1 else ''}")

    if len(partes) == 1:
        return partes[0]
    elif len(partes) == 2:
        return f"{partes[0]} e {partes[1]}"
    else:
        return f"{partes[0]}, {partes[1]} e {partes[2]}"
