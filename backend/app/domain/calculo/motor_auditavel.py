"""
Motor de Calculo Auditavel — Pipeline completo PBC -> SB -> FP/Coeficiente -> RMI.

Cada numero produzido por este modulo tem:
  - Descricao do que e (descricao)
  - Valor resultante (valor)
  - Formula aplicada (formula)
  - Fundamentacao legal (DispositivoLegal com norma, artigo, descricao)

Saidas classificadas em tres categorias:
  FATO:      dados verificados em documentos (TC, carencia, idade, vinculos)
  PROJECAO:  estimativas futuras (datas projetadas, RMI futura)
  TESE:      argumentos juridicos / estrategias (melhor regra, comparacoes)

Cada categoria carrega nivel de confianca e disclaimer.

Fundamentacao:
  - Lei 8.213/91 (Arts. 29, 53, 142)
  - Lei 9.876/99 (Art. 29-B — Fator Previdenciario)
  - EC 103/2019 (Arts. 15-21 — Regras de Transicao; Art. 26 — Regra Permanente)
  - Decreto 3.048/99 (Art. 32 — Formula do Fator Previdenciario)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from ..models.segurado import Segurado
from ..models.resultado import (
    MemoriaCalculo,
    ItemMemoria,
    DispositivoLegal,
    ResultadoRegra,
    ResultadoCalculo,
    ResultadoRequisitos,
)
from ..models.periodo import TempoContribuicao
from ..salario.pbc import (
    calcular_salario_beneficio,
    extrair_e_corrigir_salarios,
)
from ..fator_previdenciario import (
    calcular_fator_previdenciario,
    calcular_coeficiente,
    rmi_com_fator,
    rmi_com_coeficiente,
)
from ..tempo.contagem import calcular_tempo_contribuicao, calcular_carencia
from ..indices.teto_previdenciario import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data
from ..enums import Sexo, TipoBeneficio
from ..constantes import (
    DatasCorte,
    Carencia,
    COEFICIENTE_BASE,
    COEFICIENTE_INCREMENTO,
    COEFICIENTE_LIMIAR_HOMEM,
    COEFICIENTE_LIMIAR_MULHER,
    COEFICIENTE_MAXIMO,
    ALIQUOTA_ATUARIAL,
    TC_MINIMO_HOMEM_ANOS,
    TC_MINIMO_MULHER_ANOS,
    TC_MINIMO_HOMEM_PRE_EC103,
    TC_MINIMO_MULHER_PRE_EC103,
    IDADE_DEFINITIVA_HOMEM,
    IDADE_DEFINITIVA_MULHER,
    PONTOS_EC103,
    PONTOS_EC103_TETO_HOMEM,
    PONTOS_EC103_TETO_MULHER,
)


# ---------------------------------------------------------------------------
# Categorias de saida e niveis de confianca
# ---------------------------------------------------------------------------

class CategoriaResultado(str, Enum):
    """Classificacao de cada item de saida."""
    FATO = "FATO"
    PROJECAO = "PROJECAO"
    TESE = "TESE"


_DISCLAIMERS = {
    CategoriaResultado.FATO: (
        "Dados extraidos de CNIS, CTPS ou documentos apresentados. "
        "Sujeitos a retificacao administrativa ou judicial."
    ),
    CategoriaResultado.PROJECAO: (
        "Estimativa baseada na legislacao vigente e nos dados atuais. "
        "Valores futuros podem variar conforme reajustes, novas contribuicoes "
        "ou alteracoes legislativas."
    ),
    CategoriaResultado.TESE: (
        "Argumento juridico baseado em interpretacao da legislacao e jurisprudencia. "
        "Nao constitui garantia de deferimento. Depende de analise do INSS ou Poder Judiciario."
    ),
}

_CONFIANCA_PADRAO = {
    CategoriaResultado.FATO: "ALTA — dados documentais verificaveis",
    CategoriaResultado.PROJECAO: "MEDIA — estimativa sujeita a variaveis futuras",
    CategoriaResultado.TESE: "VARIAVEL — depende de posicionamento administrativo/judicial",
}


# ---------------------------------------------------------------------------
# Dispositivos legais reutilizaveis
# ---------------------------------------------------------------------------

_DL_LEI_8213_ART29 = DispositivoLegal(
    norma="Lei 8.213/91",
    artigo="Art. 29",
    descricao="Calculo do salario de beneficio",
)

_DL_LEI_9876_ART29 = DispositivoLegal(
    norma="Lei 9.876/99",
    artigo="Art. 29, I e II",
    descricao="Media dos 80% maiores salarios desde jul/1994 com divisor minimo",
)

_DL_EC103_ART26 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 26",
    descricao="Media de 100% dos salarios desde jul/1994 — regra permanente",
)

_DL_EC103_ART26_P6 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 26, par. 6",
    descricao="Descarte de contribuicoes que reduzem a media, mantida carencia minima",
)

_DL_EC103_ART26_COEF = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 26, par. 2",
    descricao="Coeficiente 60% + 2% por ano acima do limiar (20a H / 15a M)",
)

_DL_LEI_9876_FP = DispositivoLegal(
    norma="Lei 9.876/99",
    artigo="Art. 29-B",
    descricao="Formula do Fator Previdenciario: f=(Tc*a/Es)*[1+(Id+Tc*a)/100]",
)

_DL_DECRETO_3048_ART32 = DispositivoLegal(
    norma="Decreto 3.048/99",
    artigo="Art. 32",
    descricao="Regulamentacao da formula do Fator Previdenciario",
)

_DL_LEI_8213_ART53 = DispositivoLegal(
    norma="Lei 8.213/91",
    artigo="Art. 53",
    descricao="RMI da aposentadoria por tempo de contribuicao (regra pre-reforma)",
)

_DL_DECRETO_3048_ART60 = DispositivoLegal(
    norma="Decreto 3.048/99",
    artigo="Art. 60",
    descricao="Contagem de tempo de contribuicao por dias corridos para empregado/avulso",
)

_DL_LEI_8213_ART25 = DispositivoLegal(
    norma="Lei 8.213/91",
    artigo="Art. 25, II",
    descricao="Carencia de 180 contribuicoes para aposentadoria",
)

_DL_EC103_ART15 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 15",
    descricao="Regra permanente — idade minima 65a (H) / 62a (M) + TC minimo 20a (H) / 15a (M)",
)

_DL_EC103_ART16 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 16",
    descricao="Regra de transicao por pontos (idade + TC)",
)

_DL_EC103_ART17 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 17",
    descricao="Regra de transicao por idade minima progressiva + pedagio 50%",
)

_DL_EC103_ART20 = DispositivoLegal(
    norma="EC 103/2019",
    artigo="Art. 20",
    descricao="Regra de transicao por pedagio 100%",
)

_DL_TETO_RGPS = DispositivoLegal(
    norma="Lei 8.213/91",
    artigo="Art. 33",
    descricao="RMI nao pode exceder o teto do RGPS vigente na DER",
)

_DL_PISO_SM = DispositivoLegal(
    norma="CF/88",
    artigo="Art. 201, par. 2",
    descricao="Nenhum beneficio que substitua renda pode ser inferior ao salario minimo",
)


# ---------------------------------------------------------------------------
# Funcoes auxiliares internas
# ---------------------------------------------------------------------------

def _adicionar_etapa(
    memoria: MemoriaCalculo,
    descricao: str,
    valor: Any = None,
    formula: str = "",
    fundamentacao: Optional[DispositivoLegal] = None,
    nivel: int = 0,
) -> None:
    """Wrapper para MemoriaCalculo.adicionar com verificacao."""
    memoria.adicionar(
        descricao=descricao,
        valor=valor,
        formula=formula,
        nivel=nivel,
        fundamentacao=fundamentacao,
    )


def _formatar_brl(valor: Decimal) -> str:
    """Formata Decimal como moeda brasileira para exibicao na memoria."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _formatar_tc(tc: TempoContribuicao) -> str:
    """Formata TempoContribuicao legivel."""
    return f"{tc.anos}a {tc.meses_restantes}m {tc.dias_restantes}d ({tc.dias_total} dias)"


def _tc_minimo_anos(sexo: Sexo, usar_ec103: bool) -> Decimal:
    """Retorna o TC minimo em anos conforme sexo e regime."""
    if usar_ec103:
        return TC_MINIMO_HOMEM_ANOS if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_ANOS
    return TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103


def _idade_minima(sexo: Sexo) -> Decimal:
    """Idade minima definitiva (regra permanente EC 103)."""
    return IDADE_DEFINITIVA_HOMEM if sexo == Sexo.MASCULINO else IDADE_DEFINITIVA_MULHER


def _pontos_exigidos(ano: int, sexo: Sexo) -> Decimal:
    """Pontuacao exigida na regra de transicao Art. 16 EC 103/2019."""
    if ano in PONTOS_EC103:
        idx = 0 if sexo == Sexo.MASCULINO else 1
        return Decimal(str(PONTOS_EC103[ano][idx]))
    teto = PONTOS_EC103_TETO_HOMEM if sexo == Sexo.MASCULINO else PONTOS_EC103_TETO_MULHER
    return teto


def _limiar_coeficiente(sexo: Sexo) -> Decimal:
    """Limiar de anos de TC para inicio do incremento do coeficiente."""
    return COEFICIENTE_LIMIAR_HOMEM if sexo == Sexo.MASCULINO else COEFICIENTE_LIMIAR_MULHER


# ---------------------------------------------------------------------------
# ETAPA 1 — Apuracao de fatos (FATO)
# ---------------------------------------------------------------------------

def _etapa_fatos(
    segurado: Segurado,
    der: date,
    memoria: MemoriaCalculo,
) -> Dict[str, Any]:
    """
    Coleta e registra todos os fatos verificaveis do segurado na DER.
    Retorna dict com tc, carencia_meses, idade, n_vinculos.
    """
    memoria.secao("ETAPA 1 — APURACAO DE FATOS (categoria: FATO)")

    # 1.1 — Tempo de contribuicao
    tc = calcular_tempo_contribuicao(
        vinculos=segurado.vinculos,
        der=der,
        sexo=segurado.sexo,
        incluir_especial=True,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )

    _adicionar_etapa(
        memoria,
        descricao="Tempo de Contribuicao Total (TC)",
        valor=_formatar_tc(tc),
        formula=(
            f"Soma de periodos (empregado: dias corridos; CI/facult: competencias*30d) "
            f"com remocao de sobreposicoes e conversao de tempo especial. "
            f"Comum={tc.dias_comum}d + Especial convertido={tc.dias_especial_convertido}d "
            f"= {tc.dias_total}d"
        ),
        fundamentacao=_DL_DECRETO_3048_ART60,
        nivel=1,
    )

    tc_anos_decimal = tc.anos_decimal
    _adicionar_etapa(
        memoria,
        descricao="TC em anos decimais (para formulas)",
        valor=str(tc_anos_decimal.quantize(Decimal("0.0001"))),
        formula=f"{tc.dias_total} / 365.25 = {tc_anos_decimal.quantize(Decimal('0.0001'))}",
        nivel=2,
    )

    # 1.2 — Carencia
    carencia_meses = calcular_carencia(
        vinculos=segurado.vinculos,
        der=der,
        beneficios_anteriores=segurado.beneficios_anteriores,
    )

    _adicionar_etapa(
        memoria,
        descricao="Carencia (meses com contribuicao valida)",
        valor=f"{carencia_meses} meses",
        formula=(
            "Empregado: cada mes no periodo do vinculo conta 1 (Sumula 75 TNU). "
            "CI/Facult: apenas meses com contribuicao efetiva valida."
        ),
        fundamentacao=_DL_LEI_8213_ART25,
        nivel=1,
    )

    # 1.3 — Idade na DER
    idade = segurado.idade_na(der)
    idade_formatada = idade.quantize(Decimal("0.0001"))
    anos_completos = int(idade)

    _adicionar_etapa(
        memoria,
        descricao="Idade na DER",
        valor=f"{anos_completos} anos ({idade_formatada} decimal)",
        formula=(
            f"DER ({der.isoformat()}) - Data nascimento "
            f"({segurado.data_nascimento.isoformat()}) = {idade_formatada} anos"
        ),
        nivel=1,
    )

    # 1.4 — Vinculos
    n_vinculos = len(segurado.vinculos)
    _adicionar_etapa(
        memoria,
        descricao="Quantidade de vinculos",
        valor=n_vinculos,
        formula=f"Total de vinculos informados no CNIS/documentos: {n_vinculos}",
        nivel=1,
    )

    # 1.5 — Sexo
    _adicionar_etapa(
        memoria,
        descricao="Sexo do segurado",
        valor=segurado.sexo.value,
        formula="Informacao cadastral — define limiares e fatores de conversao",
        nivel=1,
    )

    return {
        "tc": tc,
        "tc_anos_decimal": tc_anos_decimal,
        "carencia_meses": carencia_meses,
        "idade": idade,
        "idade_anos_completos": anos_completos,
        "n_vinculos": n_vinculos,
    }


# ---------------------------------------------------------------------------
# ETAPA 2 — Verificacao de requisitos
# ---------------------------------------------------------------------------

def _etapa_requisitos(
    segurado: Segurado,
    der: date,
    regra_nome: str,
    usar_regra_ec103: bool,
    fatos: Dict[str, Any],
    memoria: MemoriaCalculo,
) -> ResultadoRequisitos:
    """
    Verifica se o segurado atende os requisitos da regra solicitada.
    Retorna ResultadoRequisitos.
    """
    memoria.secao("ETAPA 2 — VERIFICACAO DE REQUISITOS")

    tc: TempoContribuicao = fatos["tc"]
    carencia: int = fatos["carencia_meses"]
    idade: Decimal = fatos["idade"]
    sexo = segurado.sexo

    # Carencia exigida
    carencia_exigida = Carencia.APOSENTADORIA  # 180 meses padrao
    carencia_ok = carencia >= carencia_exigida

    _adicionar_etapa(
        memoria,
        descricao="Carencia exigida",
        valor=f"{carencia_exigida} meses",
        formula=f"Art. 25, II, Lei 8.213/91 — aposentadoria programada exige 180 meses",
        fundamentacao=_DL_LEI_8213_ART25,
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="Carencia cumprida?",
        valor="SIM" if carencia_ok else "NAO",
        formula=f"{carencia} meses cumpridos {'>=' if carencia_ok else '<'} {carencia_exigida} exigidos",
        nivel=1,
    )

    # TC minimo
    tc_minimo_a = _tc_minimo_anos(sexo, usar_regra_ec103)
    tc_minimo_dias = int(tc_minimo_a * Decimal("365.25"))
    tc_ok = tc.dias_total >= tc_minimo_dias
    faltam_dias_tc = max(0, tc_minimo_dias - tc.dias_total)

    _adicionar_etapa(
        memoria,
        descricao="TC minimo exigido",
        valor=f"{tc_minimo_a} anos ({tc_minimo_dias} dias)",
        formula=(
            f"{'EC 103/2019 Art. 15' if usar_regra_ec103 else 'Lei 8.213/91 Art. 52/53'}: "
            f"{'H' if sexo == Sexo.MASCULINO else 'M'} = {tc_minimo_a} anos"
        ),
        fundamentacao=_DL_EC103_ART15 if usar_regra_ec103 else _DL_LEI_8213_ART53,
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="TC suficiente?",
        valor="SIM" if tc_ok else f"NAO — faltam {faltam_dias_tc} dias",
        formula=f"{tc.dias_total}d {'>=' if tc_ok else '<'} {tc_minimo_dias}d",
        nivel=1,
    )

    # Idade minima (regra permanente EC 103)
    idade_min = _idade_minima(sexo)
    idade_ok = idade >= idade_min if usar_regra_ec103 else True  # pre-EC103 nao exige idade

    motivos = []
    if not carencia_ok:
        motivos.append(f"Carencia insuficiente: {carencia}/{carencia_exigida} meses")
    if not tc_ok:
        motivos.append(f"TC insuficiente: faltam {faltam_dias_tc} dias")
    if usar_regra_ec103 and not idade_ok:
        motivos.append(f"Idade insuficiente: {int(idade)} anos < {idade_min} exigidos")

    if usar_regra_ec103:
        _adicionar_etapa(
            memoria,
            descricao="Idade minima exigida (regra permanente)",
            valor=f"{idade_min} anos",
            formula=f"EC 103/2019 Art. 15: {'H' if sexo == Sexo.MASCULINO else 'M'} = {idade_min} anos",
            fundamentacao=_DL_EC103_ART15,
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="Idade suficiente?",
            valor="SIM" if idade_ok else f"NAO — {int(idade)} anos < {idade_min}",
            formula=f"{idade.quantize(Decimal('0.01'))} {'>=' if idade_ok else '<'} {idade_min}",
            nivel=1,
        )

    # Verificacao especifica por regra de transicao
    elegivel = carencia_ok and tc_ok and idade_ok
    elegivel = _verificar_regra_especifica(
        regra_nome, segurado, der, fatos, usar_regra_ec103, memoria, elegivel, motivos
    )

    faltam_meses_carencia = max(0, carencia_exigida - carencia)

    resultado_req = ResultadoRequisitos(
        elegivel=elegivel,
        carencia_ok=carencia_ok,
        carencia_meses_cumpridos=carencia,
        carencia_meses_exigidos=carencia_exigida,
        qualidade_segurado_ok=True,  # presumido — analise separada
        tempo_contribuicao=tc,
        faltam_dias=faltam_dias_tc,
        faltam_meses_carencia=faltam_meses_carencia,
        motivos_inelegibilidade=motivos,
    )

    _adicionar_etapa(
        memoria,
        descricao="ELEGIVEL para a regra?",
        valor="SIM" if elegivel else "NAO",
        formula="; ".join(motivos) if motivos else "Todos os requisitos atendidos",
        nivel=0,
    )

    return resultado_req


def _verificar_regra_especifica(
    regra_nome: str,
    segurado: Segurado,
    der: date,
    fatos: Dict[str, Any],
    usar_ec103: bool,
    memoria: MemoriaCalculo,
    elegivel_base: bool,
    motivos: List[str],
) -> bool:
    """Aplica verificacoes adicionais conforme a regra nomeada."""
    sexo = segurado.sexo
    idade = fatos["idade"]
    tc: TempoContribuicao = fatos["tc"]
    tc_anos = fatos["tc_anos_decimal"]

    regra = regra_nome.lower().strip()

    if regra in ("pontos", "art16", "transicao_pontos"):
        # Regra de pontos — Art. 16 EC 103/2019
        pontos_exig = _pontos_exigidos(der.year, sexo)
        pontos_segurado = idade + tc_anos
        pontos_ok = pontos_segurado >= pontos_exig

        # TC minimo pre-EC103 e exigido na regra de pontos
        tc_min_pre = TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103
        tc_min_pre_dias = int(tc_min_pre * Decimal("365.25"))
        tc_pre_ok = tc.dias_total >= tc_min_pre_dias

        _adicionar_etapa(
            memoria,
            descricao=f"Regra de Pontos (Art. 16) — Pontuacao exigida em {der.year}",
            valor=f"{pontos_exig} pontos",
            formula=(
                f"Tabela Art. 16 EC 103/2019 para {der.year}, "
                f"sexo {'H' if sexo == Sexo.MASCULINO else 'M'}"
            ),
            fundamentacao=_DL_EC103_ART16,
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="Pontuacao do segurado",
            valor=f"{pontos_segurado.quantize(Decimal('0.01'))} pontos",
            formula=(
                f"Idade ({idade.quantize(Decimal('0.01'))}) + "
                f"TC ({tc_anos.quantize(Decimal('0.01'))}) = "
                f"{pontos_segurado.quantize(Decimal('0.01'))}"
            ),
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="TC minimo exigido (regra de pontos)",
            valor=f"{tc_min_pre} anos",
            formula=f"Art. 16 EC 103: exige TC minimo de {tc_min_pre}a ({'H' if sexo == Sexo.MASCULINO else 'M'})",
            nivel=1,
        )

        if not pontos_ok:
            faltam_pontos = pontos_exig - pontos_segurado
            motivos.append(
                f"Pontuacao insuficiente: {pontos_segurado.quantize(Decimal('0.01'))} < {pontos_exig} "
                f"(faltam {faltam_pontos.quantize(Decimal('0.01'))} pontos)"
            )
        if not tc_pre_ok:
            motivos.append(
                f"TC insuficiente para regra de pontos: {tc.dias_total}d < {tc_min_pre_dias}d "
                f"(exige {tc_min_pre}a)"
            )

        return elegivel_base and pontos_ok and tc_pre_ok

    elif regra in ("pedagio_50", "art17_pedagio50"):
        # Pedagio 50% — Art. 17 EC 103/2019
        tc_min_pre = TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103
        tc_min_pre_dias = int(tc_min_pre * Decimal("365.25"))
        # Na data da EC 103 (13/11/2019), quanto faltava?
        tc_na_ec103 = calcular_tempo_contribuicao(
            vinculos=segurado.vinculos,
            der=DatasCorte.EC_103_2019,
            sexo=sexo,
            incluir_especial=True,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        faltava_na_ec103 = max(0, tc_min_pre_dias - tc_na_ec103.dias_total)

        # So pode usar se faltavam ate 2 anos (730 dias) na data da EC 103
        pode_usar = faltava_na_ec103 <= 730 and faltava_na_ec103 > 0

        # TC exigido = TC minimo + 50% do que faltava
        pedagio_dias = int(Decimal(str(faltava_na_ec103)) * Decimal("0.5"))
        tc_exigido_total = tc_min_pre_dias + pedagio_dias
        tc_pedagio_ok = tc.dias_total >= tc_exigido_total

        _adicionar_etapa(
            memoria,
            descricao="Pedagio 50% — TC que faltava em 13/11/2019",
            valor=f"{faltava_na_ec103} dias",
            formula=(
                f"TC minimo ({tc_min_pre}a = {tc_min_pre_dias}d) - "
                f"TC em 13/11/2019 ({tc_na_ec103.dias_total}d) = {faltava_na_ec103}d"
            ),
            fundamentacao=_DL_EC103_ART17,
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="Requisito: faltavam ate 2 anos (730d) em 13/11/2019?",
            valor="SIM" if pode_usar else "NAO — regra inaplicavel",
            formula=f"{faltava_na_ec103}d {'<=' if pode_usar else '>'} 730d",
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="TC total exigido com pedagio",
            valor=f"{tc_exigido_total} dias",
            formula=f"{tc_min_pre_dias}d + 50% * {faltava_na_ec103}d = {tc_min_pre_dias} + {pedagio_dias} = {tc_exigido_total}d",
            nivel=1,
        )

        if not pode_usar:
            motivos.append("Regra do Pedagio 50% inaplicavel: faltavam mais de 2 anos em 13/11/2019")
        if not tc_pedagio_ok:
            motivos.append(f"TC insuficiente com pedagio: {tc.dias_total}d < {tc_exigido_total}d")

        return elegivel_base and pode_usar and tc_pedagio_ok

    elif regra in ("pedagio_100", "art20_pedagio100"):
        # Pedagio 100% — Art. 20 EC 103/2019
        tc_min_pre = TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103
        tc_min_pre_dias = int(tc_min_pre * Decimal("365.25"))
        tc_na_ec103 = calcular_tempo_contribuicao(
            vinculos=segurado.vinculos,
            der=DatasCorte.EC_103_2019,
            sexo=sexo,
            incluir_especial=True,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        faltava_na_ec103 = max(0, tc_min_pre_dias - tc_na_ec103.dias_total)
        pedagio_dias = faltava_na_ec103  # 100%
        tc_exigido_total = tc_min_pre_dias + pedagio_dias
        tc_pedagio_ok = tc.dias_total >= tc_exigido_total

        # Idade minima: 57 M / 60 H
        idade_min_ped100 = Decimal("60") if sexo == Sexo.MASCULINO else Decimal("57")
        idade_ok = idade >= idade_min_ped100

        _adicionar_etapa(
            memoria,
            descricao="Pedagio 100% — TC que faltava em 13/11/2019",
            valor=f"{faltava_na_ec103} dias",
            formula=(
                f"TC minimo ({tc_min_pre}a = {tc_min_pre_dias}d) - "
                f"TC em 13/11/2019 ({tc_na_ec103.dias_total}d) = {faltava_na_ec103}d"
            ),
            fundamentacao=_DL_EC103_ART20,
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="TC total exigido com pedagio 100%",
            valor=f"{tc_exigido_total} dias",
            formula=f"{tc_min_pre_dias}d + 100% * {faltava_na_ec103}d = {tc_exigido_total}d",
            nivel=1,
        )
        _adicionar_etapa(
            memoria,
            descricao="Idade minima pedagio 100%",
            valor=f"{idade_min_ped100} anos",
            formula=f"Art. 20 EC 103: {'H' if sexo == Sexo.MASCULINO else 'M'} = {idade_min_ped100}a",
            nivel=1,
        )

        if not tc_pedagio_ok:
            motivos.append(f"TC insuficiente com pedagio 100%: {tc.dias_total}d < {tc_exigido_total}d")
        if not idade_ok:
            motivos.append(f"Idade insuficiente pedagio 100%: {int(idade)}a < {idade_min_ped100}a")

        return elegivel_base and tc_pedagio_ok and idade_ok

    elif regra in ("regra_permanente", "art15", "permanente"):
        # Ja verificado na base — nada adicional
        return elegivel_base

    elif regra in ("pre_reforma", "pre_ec103", "direito_adquirido"):
        # Direito adquirido antes da EC 103
        # O segurado precisa ter completado os requisitos ATE 13/11/2019
        tc_na_ec103 = calcular_tempo_contribuicao(
            vinculos=segurado.vinculos,
            der=DatasCorte.EC_103_2019,
            sexo=sexo,
            incluir_especial=True,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        carencia_na_ec103 = calcular_carencia(
            vinculos=segurado.vinculos,
            der=DatasCorte.EC_103_2019,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        tc_min_pre = TC_MINIMO_HOMEM_PRE_EC103 if sexo == Sexo.MASCULINO else TC_MINIMO_MULHER_PRE_EC103
        tc_min_dias = int(tc_min_pre * Decimal("365.25"))

        direito_ok = (tc_na_ec103.dias_total >= tc_min_dias and carencia_na_ec103 >= Carencia.APOSENTADORIA)

        _adicionar_etapa(
            memoria,
            descricao="Verificacao de direito adquirido antes de 13/11/2019",
            valor="SIM" if direito_ok else "NAO",
            formula=(
                f"TC em 13/11/2019 = {tc_na_ec103.dias_total}d (exigido {tc_min_dias}d); "
                f"Carencia = {carencia_na_ec103}m (exigido {Carencia.APOSENTADORIA}m)"
            ),
            nivel=1,
        )

        if not direito_ok:
            motivos.append("Sem direito adquirido pre-EC 103: requisitos nao cumpridos ate 13/11/2019")

        return direito_ok

    # Regra generica — retornar elegibilidade base
    return elegivel_base


# ---------------------------------------------------------------------------
# ETAPA 3 — Calculo do Salario de Beneficio (SB)
# ---------------------------------------------------------------------------

def _etapa_salario_beneficio(
    segurado: Segurado,
    der: date,
    usar_regra_ec103: bool,
    carencia_exigida: int,
    memoria: MemoriaCalculo,
) -> Dict[str, Any]:
    """
    Calcula o Salario de Beneficio e registra cada passo na memoria.
    Retorna dict com sb, media, n_salarios, divisor, salarios_pbc, regra_aplicada.
    """
    memoria.secao("ETAPA 3 — CALCULO DO SALARIO DE BENEFICIO (SB)")

    resultado_sb = calcular_salario_beneficio(
        vinculos=segurado.vinculos,
        der=der,
        usar_regra_ec103=usar_regra_ec103,
        incluir_pre_1994=False,
        aplicar_descarte=usar_regra_ec103,
        meses_carencia_exigidos=carencia_exigida,
    )

    sb = resultado_sb["salario_beneficio"]
    media = resultado_sb["media"]
    n_salarios = resultado_sb["n_salarios"]
    divisor = resultado_sb["divisor"]
    n_descartados = resultado_sb["salarios_descartados"]
    regra_aplicada = resultado_sb["regra_aplicada"]
    salarios_pbc = resultado_sb["salarios_pbc"]

    # 3.1 — Extracao de salarios
    salarios_brutos = extrair_e_corrigir_salarios(segurado.vinculos, der, incluir_pre_1994=False)
    n_brutos = len(salarios_brutos)

    _adicionar_etapa(
        memoria,
        descricao="Salarios extraidos do PBC (jul/1994 ate DER-1)",
        valor=f"{n_brutos} contribuicoes",
        formula=(
            f"Extrai todos os SC dos vinculos, aplica teto vigente em cada competencia, "
            f"corrige monetariamente (INPC) ate {der.isoformat()}, remove duplicatas por competencia"
        ),
        fundamentacao=_DL_LEI_8213_ART29,
        nivel=1,
    )

    if n_brutos > 0:
        menor = min(c.salario_corrigido for c in salarios_brutos)
        maior = max(c.salario_corrigido for c in salarios_brutos)
        soma_total = sum(c.salario_corrigido for c in salarios_brutos)
        _adicionar_etapa(
            memoria,
            descricao="Faixa de salarios corrigidos",
            valor=f"Menor: {_formatar_brl(menor)} | Maior: {_formatar_brl(maior)}",
            formula=f"Soma total corrigida: {_formatar_brl(soma_total)}",
            nivel=2,
        )

    # 3.2 — Regra de selecao
    if usar_regra_ec103:
        _adicionar_etapa(
            memoria,
            descricao="Regra do PBC aplicada",
            valor="EC 103/2019 — 100% dos salarios",
            formula=(
                f"Media aritmetica simples de TODOS os {n_brutos} SC desde jul/1994. "
                f"Art. 26, par. 1: nao se descartam os 20% menores."
            ),
            fundamentacao=_DL_EC103_ART26,
            nivel=1,
        )

        if n_descartados > 0:
            _adicionar_etapa(
                memoria,
                descricao="Descarte automatico (Art. 26, par. 6)",
                valor=f"{n_descartados} contribuicoes descartadas",
                formula=(
                    f"Descarte de {n_descartados} contribuicoes de menor valor que "
                    f"aumentam a media, mantendo {n_salarios} >= {carencia_exigida} (carencia)"
                ),
                fundamentacao=_DL_EC103_ART26_P6,
                nivel=2,
            )
    else:
        _adicionar_etapa(
            memoria,
            descricao="Regra do PBC aplicada",
            valor="Lei 9.876/99 — 80% maiores com divisor minimo",
            formula=(
                f"Seleciona os {n_salarios} maiores SC (80% de {n_brutos}). "
                f"Divisor = max(60% * {n_brutos}, {n_salarios}) = {divisor}."
            ),
            fundamentacao=_DL_LEI_9876_ART29,
            nivel=1,
        )

    # 3.3 — Media / SB
    if n_salarios > 0 and salarios_pbc:
        soma_sel = sum(c.salario_corrigido for c in salarios_pbc)
        _adicionar_etapa(
            memoria,
            descricao="Soma dos salarios selecionados",
            valor=_formatar_brl(soma_sel),
            formula=f"Soma de {n_salarios} SC corrigidos selecionados",
            nivel=2,
        )

    _adicionar_etapa(
        memoria,
        descricao="SALARIO DE BENEFICIO (SB)",
        valor=_formatar_brl(sb),
        formula=f"SB = Soma / Divisor = media de {n_salarios} SC (divisor={divisor}) = {_formatar_brl(media)}",
        fundamentacao=_DL_EC103_ART26 if usar_regra_ec103 else _DL_LEI_9876_ART29,
        nivel=0,
    )

    return {
        "sb": sb,
        "media": media,
        "n_salarios": n_salarios,
        "divisor": divisor,
        "salarios_pbc": salarios_pbc,
        "n_descartados": n_descartados,
        "regra_aplicada": regra_aplicada,
    }


# ---------------------------------------------------------------------------
# ETAPA 4 — Fator Previdenciario ou Coeficiente
# ---------------------------------------------------------------------------

def _etapa_fator_ou_coeficiente(
    segurado: Segurado,
    der: date,
    regra_nome: str,
    usar_regra_ec103: bool,
    fatos: Dict[str, Any],
    memoria: MemoriaCalculo,
) -> Dict[str, Any]:
    """
    Calcula FP ou coeficiente conforme a regra.
    Retorna dict com tipo ('fator' ou 'coeficiente'), valor, e detalhes.
    """
    memoria.secao("ETAPA 4 — FATOR PREVIDENCIARIO / COEFICIENTE")

    sexo = segurado.sexo
    tc_anos = fatos["tc_anos_decimal"]
    idade = fatos["idade"]
    regra = regra_nome.lower().strip()

    # Regras que usam Fator Previdenciario
    usa_fator = regra in (
        "pedagio_50", "art17_pedagio50",
        "pre_reforma", "pre_ec103", "direito_adquirido",
    )

    if usa_fator:
        # Fator Previdenciario
        fp = calcular_fator_previdenciario(tc_anos, idade, der)

        _adicionar_etapa(
            memoria,
            descricao="Calculo do FATOR PREVIDENCIARIO",
            valor=str(fp),
            formula=(
                f"f = (Tc * a / Es) * [1 + (Id + Tc * a) / 100]\n"
                f"  Tc = {tc_anos.quantize(Decimal('0.0001'))} anos\n"
                f"  a  = {ALIQUOTA_ATUARIAL} (aliquota atuarial fixa)\n"
                f"  Id = {idade.quantize(Decimal('0.0001'))} anos\n"
                f"  Es = expectativa de sobrevida (tabua IBGE {der.year}, idade {int(idade)})\n"
                f"  f  = {fp}"
            ),
            fundamentacao=_DL_LEI_9876_FP,
            nivel=1,
        )

        # Bonus por sexo — mulher ganha +5 anos, professor +5/+10
        # (simplificado aqui — bonus esta embutido no tc_anos do segurado)
        _adicionar_etapa(
            memoria,
            descricao="Observacao sobre o Fator",
            valor="MAIOR que 1 — bonifica" if fp > Decimal("1") else "MENOR que 1 — penaliza",
            formula=(
                f"FP {'>' if fp > Decimal('1') else '<'} 1.0: "
                f"{'beneficio sera maior' if fp > Decimal('1') else 'beneficio sera reduzido'} "
                f"em relacao ao SB"
            ),
            fundamentacao=_DL_DECRETO_3048_ART32,
            nivel=2,
        )

        return {"tipo": "fator", "valor": fp}

    else:
        # Coeficiente EC 103/2019
        coef = calcular_coeficiente(tc_anos, sexo)
        limiar = _limiar_coeficiente(sexo)
        anos_excedentes = max(Decimal("0"), tc_anos - limiar)
        percentual = (coef * Decimal("100")).quantize(Decimal("0.01"))

        _adicionar_etapa(
            memoria,
            descricao="Calculo do COEFICIENTE (EC 103/2019)",
            valor=f"{percentual}%",
            formula=(
                f"Coef = 60% + 2% * max(0, TC - limiar)\n"
                f"  TC     = {tc_anos.quantize(Decimal('0.0001'))} anos\n"
                f"  Limiar = {limiar} anos ({'H' if sexo == Sexo.MASCULINO else 'M'})\n"
                f"  Excedente = max(0, {tc_anos.quantize(Decimal('0.01'))} - {limiar}) "
                f"= {anos_excedentes.quantize(Decimal('0.01'))} anos\n"
                f"  Coef = 60% + 2% * {anos_excedentes.quantize(Decimal('0.01'))} "
                f"= {percentual}% (limitado a {COEFICIENTE_MAXIMO * 100}%)\n"
                f"  Coef decimal = {coef}"
            ),
            fundamentacao=_DL_EC103_ART26_COEF,
            nivel=1,
        )

        return {"tipo": "coeficiente", "valor": coef}


# ---------------------------------------------------------------------------
# ETAPA 5 — Calculo da RMI
# ---------------------------------------------------------------------------

def _etapa_rmi(
    der: date,
    sb: Decimal,
    fator_ou_coef: Dict[str, Any],
    memoria: MemoriaCalculo,
) -> Tuple[Decimal, Decimal]:
    """
    Aplica FP ou coeficiente ao SB, limita ao teto e piso.
    Retorna (rmi_bruta, rmi_teto).
    """
    memoria.secao("ETAPA 5 — CALCULO DA RMI (Renda Mensal Inicial)")

    teto = teto_na_data(der)
    piso = salario_minimo_na_data(der)

    _adicionar_etapa(
        memoria,
        descricao="Teto do RGPS na DER",
        valor=_formatar_brl(teto),
        formula=f"Portaria MPS vigente em {der.isoformat()}: teto = {_formatar_brl(teto)}",
        fundamentacao=_DL_TETO_RGPS,
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="Piso (salario minimo) na DER",
        valor=_formatar_brl(piso),
        formula=f"Decreto vigente em {der.isoformat()}: SM = {_formatar_brl(piso)}",
        fundamentacao=_DL_PISO_SM,
        nivel=1,
    )

    tipo = fator_ou_coef["tipo"]
    valor_fc = fator_ou_coef["valor"]

    if tipo == "fator":
        rmi_bruta = (sb * valor_fc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rmi_final = rmi_com_fator(sb, valor_fc, teto)
        rmi_final = max(rmi_final, piso)

        _adicionar_etapa(
            memoria,
            descricao="RMI bruta (SB * FP)",
            valor=_formatar_brl(rmi_bruta),
            formula=f"RMI = SB * FP = {_formatar_brl(sb)} * {valor_fc} = {_formatar_brl(rmi_bruta)}",
            nivel=1,
        )
    else:
        rmi_bruta = (sb * valor_fc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rmi_final = rmi_com_coeficiente(sb, valor_fc, teto, piso)

        percentual = (valor_fc * Decimal("100")).quantize(Decimal("0.01"))
        _adicionar_etapa(
            memoria,
            descricao="RMI bruta (SB * Coeficiente)",
            valor=_formatar_brl(rmi_bruta),
            formula=f"RMI = SB * {percentual}% = {_formatar_brl(sb)} * {valor_fc} = {_formatar_brl(rmi_bruta)}",
            nivel=1,
        )

    # Limitacao ao teto
    if rmi_bruta > teto:
        _adicionar_etapa(
            memoria,
            descricao="Limitacao ao teto do RGPS",
            valor=_formatar_brl(teto),
            formula=f"RMI bruta {_formatar_brl(rmi_bruta)} > Teto {_formatar_brl(teto)} — limitada ao teto",
            fundamentacao=_DL_TETO_RGPS,
            nivel=1,
        )

    # Garantia do piso
    if rmi_final <= piso and rmi_bruta < piso:
        _adicionar_etapa(
            memoria,
            descricao="Garantia do salario minimo",
            valor=_formatar_brl(piso),
            formula=f"RMI {_formatar_brl(rmi_bruta)} < SM {_formatar_brl(piso)} — elevada ao SM",
            fundamentacao=_DL_PISO_SM,
            nivel=1,
        )

    _adicionar_etapa(
        memoria,
        descricao="RMI FINAL",
        valor=_formatar_brl(rmi_final),
        formula=(
            f"RMI = max(SM, min(RMI_bruta, Teto)) = "
            f"max({_formatar_brl(piso)}, min({_formatar_brl(rmi_bruta)}, {_formatar_brl(teto)})) "
            f"= {_formatar_brl(rmi_final)}"
        ),
        nivel=0,
    )

    return rmi_bruta, rmi_final


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL — calcular_auditavel
# ---------------------------------------------------------------------------

def calcular_auditavel(
    segurado: Segurado,
    der: date,
    regra_nome: str,
    usar_regra_ec103: bool = True,
) -> ResultadoCalculo:
    """
    Pipeline completo de calculo previdenciario auditavel.

    Fluxo:
      1. FATOS — apura TC, carencia, idade, vinculos
      2. REQUISITOS — verifica elegibilidade para a regra
      3. PBC -> SB — calcula salario de beneficio
      4. FP ou COEFICIENTE — aplica fator ou coeficiente
      5. RMI — calcula renda mensal inicial com teto e piso

    Cada passo e registrado na MemoriaCalculo com descricao, valor,
    formula e fundamentacao legal (DispositivoLegal).

    Args:
        segurado: dados completos do segurado (pessoais, vinculos, contribuicoes)
        der: Data de Entrada do Requerimento
        regra_nome: qual regra calcular. Opcoes:
            - "regra_permanente" / "art15" / "permanente"
            - "pontos" / "art16" / "transicao_pontos"
            - "pedagio_50" / "art17_pedagio50"
            - "pedagio_100" / "art20_pedagio100"
            - "pre_reforma" / "pre_ec103" / "direito_adquirido"
        usar_regra_ec103: True para regras pos-reforma (media de 100%),
                          False para regras pre-reforma (80% maiores)

    Returns:
        ResultadoCalculo completo com memoria de calculo auditavel.
    """
    memoria = MemoriaCalculo()
    avisos: List[str] = []
    erros: List[str] = []
    fundamentacao_legal: List[DispositivoLegal] = []

    # Cabecalho
    memoria.secao("CALCULO PREVIDENCIARIO AUDITAVEL")
    _adicionar_etapa(
        memoria,
        descricao="Data do calculo",
        valor=date.today().isoformat(),
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="Segurado",
        valor=segurado.dados_pessoais.nome,
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="DER (Data de Entrada do Requerimento)",
        valor=der.isoformat(),
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="Regra solicitada",
        valor=regra_nome,
        nivel=1,
    )
    _adicionar_etapa(
        memoria,
        descricao="Regime de calculo do SB",
        valor="EC 103/2019 (100%)" if usar_regra_ec103 else "Lei 9.876/99 (80%)",
        nivel=1,
    )

    # Determinar tipo de beneficio
    tipo_beneficio = _inferir_tipo_beneficio(regra_nome)

    # ── ETAPA 1 — Fatos ─────────────────────────────────────────────────
    try:
        fatos = _etapa_fatos(segurado, der, memoria)
    except Exception as e:
        erros.append(f"Erro na apuracao de fatos: {str(e)}")
        return _resultado_com_erro(tipo_beneficio, der, memoria, erros)

    # ── ETAPA 2 — Requisitos ────────────────────────────────────────────
    try:
        requisitos = _etapa_requisitos(
            segurado, der, regra_nome, usar_regra_ec103, fatos, memoria
        )
    except Exception as e:
        erros.append(f"Erro na verificacao de requisitos: {str(e)}")
        return _resultado_com_erro(tipo_beneficio, der, memoria, erros)

    # ── ETAPA 3 — Salario de Beneficio ──────────────────────────────────
    try:
        dados_sb = _etapa_salario_beneficio(
            segurado, der, usar_regra_ec103,
            Carencia.APOSENTADORIA, memoria,
        )
    except Exception as e:
        erros.append(f"Erro no calculo do salario de beneficio: {str(e)}")
        return _resultado_com_erro(tipo_beneficio, der, memoria, erros)

    sb = dados_sb["sb"]

    # ── ETAPA 4 — Fator / Coeficiente ──────────────────────────────────
    try:
        fator_ou_coef = _etapa_fator_ou_coeficiente(
            segurado, der, regra_nome, usar_regra_ec103, fatos, memoria,
        )
    except Exception as e:
        erros.append(f"Erro no calculo do fator/coeficiente: {str(e)}")
        return _resultado_com_erro(tipo_beneficio, der, memoria, erros)

    # ── ETAPA 5 — RMI ──────────────────────────────────────────────────
    try:
        rmi_bruta, rmi_final = _etapa_rmi(der, sb, fator_ou_coef, memoria)
    except Exception as e:
        erros.append(f"Erro no calculo da RMI: {str(e)}")
        return _resultado_com_erro(tipo_beneficio, der, memoria, erros)

    # ── Montar ResultadoRegra ───────────────────────────────────────────
    resultado_regra = ResultadoRegra(
        nome_regra=regra_nome,
        base_legal=_base_legal_da_regra(regra_nome),
        elegivel=requisitos.elegivel,
        rmi=rmi_bruta,
        rmi_teto=rmi_final,
        salario_beneficio=sb,
        fator_previdenciario=(
            fator_ou_coef["valor"] if fator_ou_coef["tipo"] == "fator" else None
        ),
        coeficiente=(
            fator_ou_coef["valor"] if fator_ou_coef["tipo"] == "coeficiente" else Decimal("0")
        ),
        tempo_contribuicao=fatos["tc"],
        data_implementacao=der if requisitos.elegivel else None,
        faltam_dias=requisitos.faltam_dias,
        memoria=memoria,
        avisos=avisos,
    )

    # ── Avisos ──────────────────────────────────────────────────────────
    if not requisitos.elegivel:
        avisos.append(
            f"Segurado NAO elegivel para '{regra_nome}' na DER {der.isoformat()}. "
            f"Motivos: {'; '.join(requisitos.motivos_inelegibilidade)}"
        )
    if sb <= Decimal("0"):
        avisos.append("Salario de beneficio zerado — sem contribuicoes no PBC.")
    if rmi_final == salario_minimo_na_data(der) and rmi_bruta < salario_minimo_na_data(der):
        avisos.append("RMI elevada ao salario minimo (CF Art. 201, par. 2).")

    # ── Fundamentacao consolidada ───────────────────────────────────────
    fundamentacao_legal = _consolidar_fundamentacao(memoria)

    # ── Montar ResultadoCalculo ─────────────────────────────────────────
    resultado = ResultadoCalculo(
        tipo_beneficio=tipo_beneficio,
        der=der,
        elegivel=requisitos.elegivel,
        resultado_principal=resultado_regra,
        cenarios=[resultado_regra],
        requisitos=requisitos,
        pbc=dados_sb.get("salarios_pbc", []),
        media_salarios=dados_sb.get("media", Decimal("0")),
        memoria=memoria,
        fundamentacao_legal=fundamentacao_legal,
        avisos=avisos,
        erros=erros,
    )

    return resultado


# ---------------------------------------------------------------------------
# FUNCAO AUXILIAR — gerar_relatorio_auditavel
# ---------------------------------------------------------------------------

def gerar_relatorio_auditavel(resultado: ResultadoCalculo) -> Dict[str, Any]:
    """
    Gera relatorio JSON-serializavel com separacao FATO / PROJECAO / TESE.

    Estrutura do relatorio:
    {
        "cabecalho": {...},
        "fatos": { "itens": [...], "confianca": "...", "disclaimer": "..." },
        "projecoes": { "itens": [...], "confianca": "...", "disclaimer": "..." },
        "teses": { "itens": [...], "confianca": "...", "disclaimer": "..." },
        "memoria_completa": [...],
        "fundamentacao_legal": [...],
        "avisos": [...],
        "erros": [...],
        "resumo": {...}
    }
    """
    # ── Cabecalho ───────────────────────────────────────────────────────
    cabecalho = {
        "tipo_beneficio": resultado.tipo_beneficio.value if resultado.tipo_beneficio else "",
        "der": resultado.der.isoformat(),
        "elegivel": resultado.elegivel,
        "data_geracao": date.today().isoformat(),
    }

    if resultado.resultado_principal:
        rp = resultado.resultado_principal
        cabecalho["regra"] = rp.nome_regra
        cabecalho["base_legal"] = rp.base_legal
        cabecalho["rmi_final"] = str(rp.rmi_teto)
        cabecalho["salario_beneficio"] = str(rp.salario_beneficio)

    # ── Classificar itens da memoria ────────────────────────────────────
    fatos_itens = []
    projecoes_itens = []
    teses_itens = []

    for item in resultado.memoria.itens:
        classificado = _classificar_item(item)
        item_dict = _item_para_dict(item)

        if classificado == CategoriaResultado.FATO:
            fatos_itens.append(item_dict)
        elif classificado == CategoriaResultado.PROJECAO:
            projecoes_itens.append(item_dict)
        else:
            teses_itens.append(item_dict)

    # ── Montar categorias ───────────────────────────────────────────────
    fatos_sec = {
        "categoria": CategoriaResultado.FATO.value,
        "itens": fatos_itens,
        "confianca": _CONFIANCA_PADRAO[CategoriaResultado.FATO],
        "disclaimer": _DISCLAIMERS[CategoriaResultado.FATO],
        "total_itens": len(fatos_itens),
    }

    projecoes_sec = {
        "categoria": CategoriaResultado.PROJECAO.value,
        "itens": projecoes_itens,
        "confianca": _CONFIANCA_PADRAO[CategoriaResultado.PROJECAO],
        "disclaimer": _DISCLAIMERS[CategoriaResultado.PROJECAO],
        "total_itens": len(projecoes_itens),
    }

    teses_sec = {
        "categoria": CategoriaResultado.TESE.value,
        "itens": teses_itens,
        "confianca": _CONFIANCA_PADRAO[CategoriaResultado.TESE],
        "disclaimer": _DISCLAIMERS[CategoriaResultado.TESE],
        "total_itens": len(teses_itens),
    }

    # ── Memoria completa linearizada ────────────────────────────────────
    memoria_completa = [_item_para_dict(item) for item in resultado.memoria.itens]

    # ── Fundamentacao consolidada ───────────────────────────────────────
    fundamentacao = [
        {
            "norma": dl.norma,
            "artigo": dl.artigo,
            "descricao": dl.descricao,
            "url_referencia": dl.url_referencia,
        }
        for dl in resultado.fundamentacao_legal
    ]

    # ── Resumo executivo ────────────────────────────────────────────────
    resumo = _gerar_resumo(resultado)

    return {
        "cabecalho": cabecalho,
        "fatos": fatos_sec,
        "projecoes": projecoes_sec,
        "teses": teses_sec,
        "memoria_completa": memoria_completa,
        "fundamentacao_legal": fundamentacao,
        "avisos": resultado.avisos,
        "erros": resultado.erros,
        "resumo": resumo,
    }


# ---------------------------------------------------------------------------
# Classificacao de itens em FATO / PROJECAO / TESE
# ---------------------------------------------------------------------------

# Palavras-chave para classificacao automatica
_KEYWORDS_FATO = {
    "tempo de contribuicao", "carencia", "idade na der", "quantidade de vinculos",
    "sexo do segurado", "salarios extraidos", "faixa de salarios", "soma dos salarios",
    "tc em anos", "tc minimo", "tc total", "tc que faltava",
    "pontuacao do segurado", "salario de beneficio", "der",
    "segurado", "data do calculo", "calculo previdenciario",
    "regime de calculo", "regra solicitada", "regra do pbc",
    "carencia exigida", "carencia cumprida", "tc suficiente",
    "idade minima", "idade suficiente", "descarte automatico",
    "teto do rgps", "piso", "rmi bruta", "rmi final",
    "limitacao ao teto", "garantia do salario", "fator previdenciario",
    "coeficiente",
}

_KEYWORDS_PROJECAO = {
    "projecao", "estimativa", "futuro", "projetada", "projetado",
    "data de implementacao", "faltam", "quando atingira",
}

_KEYWORDS_TESE = {
    "tese", "estrategia", "melhor regra", "recomendacao", "argumento",
    "direito adquirido", "elegivel para a regra", "regra de pontos",
    "pedagio", "observacao sobre o fator", "verificacao de direito",
    "requisito:", "inaplicavel",
}


def _classificar_item(item: ItemMemoria) -> CategoriaResultado:
    """
    Classifica um item da memoria em FATO, PROJECAO ou TESE
    com base no conteudo da descricao e formula.
    """
    texto = (item.descricao + " " + item.formula).lower()

    # Secoes (cabecalhos) sao FATO por padrao
    if item.descricao.startswith("──"):
        secao_lower = item.descricao.lower()
        if "projecao" in secao_lower or "estimativa" in secao_lower:
            return CategoriaResultado.PROJECAO
        if "tese" in secao_lower or "estrategia" in secao_lower:
            return CategoriaResultado.TESE
        return CategoriaResultado.FATO

    # Projecao tem prioridade sobre tese (itens futuros)
    for kw in _KEYWORDS_PROJECAO:
        if kw in texto:
            return CategoriaResultado.PROJECAO

    # Tese
    for kw in _KEYWORDS_TESE:
        if kw in texto:
            return CategoriaResultado.TESE

    # Default: FATO
    return CategoriaResultado.FATO


def _item_para_dict(item: ItemMemoria) -> Dict[str, Any]:
    """Converte ItemMemoria para dict JSON-serializavel."""
    d: Dict[str, Any] = {
        "descricao": item.descricao,
        "valor": _serializar_valor(item.valor),
        "formula": item.formula,
        "nivel": item.nivel,
    }
    if item.fundamentacao:
        d["fundamentacao"] = {
            "norma": item.fundamentacao.norma,
            "artigo": item.fundamentacao.artigo,
            "descricao": item.fundamentacao.descricao,
        }
    return d


def _serializar_valor(valor: Any) -> Any:
    """Converte valor para tipo JSON-serializavel."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor) if not isinstance(valor, (int, float, bool, str, list, dict)) else valor


# ---------------------------------------------------------------------------
# Funcoes auxiliares de montagem
# ---------------------------------------------------------------------------

def _inferir_tipo_beneficio(regra_nome: str) -> TipoBeneficio:
    """Infere o tipo de beneficio a partir do nome da regra."""
    regra = regra_nome.lower().strip()
    if "idade" in regra:
        return TipoBeneficio.APOSENTADORIA_IDADE
    if "especial" in regra:
        return TipoBeneficio.APOSENTADORIA_ESPECIAL
    if any(k in regra for k in ("pontos", "pedagio", "transicao", "permanente", "art15", "art16", "art17", "art20")):
        return TipoBeneficio.APOSENTADORIA_IDADE
    if "pre_reforma" in regra or "pre_ec103" in regra or "direito_adquirido" in regra:
        return TipoBeneficio.APOSENTADORIA_TEMPO_CONTRIB
    return TipoBeneficio.APOSENTADORIA_IDADE


def _base_legal_da_regra(regra_nome: str) -> str:
    """Retorna referencia legal simplificada da regra."""
    mapa = {
        "regra_permanente": "EC 103/2019 Art. 15",
        "art15": "EC 103/2019 Art. 15",
        "permanente": "EC 103/2019 Art. 15",
        "pontos": "EC 103/2019 Art. 16",
        "art16": "EC 103/2019 Art. 16",
        "transicao_pontos": "EC 103/2019 Art. 16",
        "pedagio_50": "EC 103/2019 Art. 17",
        "art17_pedagio50": "EC 103/2019 Art. 17",
        "pedagio_100": "EC 103/2019 Art. 20",
        "art20_pedagio100": "EC 103/2019 Art. 20",
        "pre_reforma": "Lei 8.213/91 Arts. 52-53 + Lei 9.876/99 Art. 29",
        "pre_ec103": "Lei 8.213/91 Arts. 52-53 + Lei 9.876/99 Art. 29",
        "direito_adquirido": "Lei 8.213/91 Arts. 52-53 + Lei 9.876/99 Art. 29",
    }
    return mapa.get(regra_nome.lower().strip(), f"Regra: {regra_nome}")


def _consolidar_fundamentacao(memoria: MemoriaCalculo) -> List[DispositivoLegal]:
    """Extrai dispositivos legais unicos da memoria."""
    vistos = set()
    dispositivos = []
    for item in memoria.itens:
        if item.fundamentacao:
            chave = (item.fundamentacao.norma, item.fundamentacao.artigo)
            if chave not in vistos:
                vistos.add(chave)
                dispositivos.append(item.fundamentacao)
    return dispositivos


def _gerar_resumo(resultado: ResultadoCalculo) -> Dict[str, Any]:
    """Gera resumo executivo do calculo."""
    resumo: Dict[str, Any] = {
        "elegivel": resultado.elegivel,
        "der": resultado.der.isoformat(),
    }

    if resultado.resultado_principal:
        rp = resultado.resultado_principal
        resumo["regra"] = rp.nome_regra
        resumo["rmi_final"] = str(rp.rmi_teto)
        resumo["rmi_formatada"] = rp.rmi_formatada
        resumo["salario_beneficio"] = str(rp.salario_beneficio)

        if rp.fator_previdenciario is not None:
            resumo["fator_previdenciario"] = str(rp.fator_previdenciario)
        if rp.coeficiente > Decimal("0"):
            resumo["coeficiente"] = str(rp.coeficiente)
            resumo["coeficiente_percentual"] = str(
                (rp.coeficiente * Decimal("100")).quantize(Decimal("0.01"))
            ) + "%"

        if rp.tempo_contribuicao:
            resumo["tempo_contribuicao"] = rp.tempo_contribuicao.formatar()
            resumo["tempo_contribuicao_dias"] = rp.tempo_contribuicao.dias_total

        if not resultado.elegivel and rp.faltam_dias > 0:
            resumo["faltam_dias"] = rp.faltam_dias
            resumo["faltam_anos_aprox"] = str(
                (Decimal(str(rp.faltam_dias)) / Decimal("365.25")).quantize(Decimal("0.1"))
            )

    if resultado.requisitos:
        req = resultado.requisitos
        resumo["carencia_cumprida"] = req.carencia_meses_cumpridos
        resumo["carencia_exigida"] = req.carencia_meses_exigidos
        resumo["motivos_inelegibilidade"] = req.motivos_inelegibilidade

    resumo["total_avisos"] = len(resultado.avisos)
    resumo["total_erros"] = len(resultado.erros)
    resumo["total_etapas_memoria"] = len(resultado.memoria.itens)
    resumo["total_dispositivos_legais"] = len(resultado.fundamentacao_legal)

    return resumo


def _resultado_com_erro(
    tipo_beneficio: TipoBeneficio,
    der: date,
    memoria: MemoriaCalculo,
    erros: List[str],
) -> ResultadoCalculo:
    """Monta ResultadoCalculo em caso de erro."""
    _adicionar_etapa(
        memoria,
        descricao="ERRO NO CALCULO",
        valor="; ".join(erros),
        nivel=0,
    )
    return ResultadoCalculo(
        tipo_beneficio=tipo_beneficio,
        der=der,
        elegivel=False,
        memoria=memoria,
        erros=erros,
    )
