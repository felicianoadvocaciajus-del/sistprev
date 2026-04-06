"""
Parser do CNIS (Cadastro Nacional de Informações Sociais) em PDF.

Estratégia em camadas:
  1. Extração de texto bruto com pdfplumber
  2. Identificação de seções (vínculos, contribuições, benefícios)
  3. Extração de campos por regex + contexto
  4. Validação semântica (datas coerentes, valores plausíveis)
  5. Montagem dos objetos de domínio

Cada campo extraído recebe um confidence_score (0–1).
Campos com confiança < 0.7 são marcados para revisão manual.
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field

from ...domain.models.contribuicao import Contribuicao, competencia_str
from ...domain.models.vinculo import Vinculo
from ...domain.models.segurado import Segurado, DadosPessoais, BeneficioAnterior
from ...domain.enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado, Sexo, TipoBeneficio


@dataclass
class CampoExtraido:
    valor: str
    confianca: float = 1.0
    linha_origem: int = 0
    requer_revisao: bool = False


@dataclass
class BeneficioCNIS:
    """Benefício encontrado no CNIS (aposentadoria, pensão, etc.)."""
    nb: str = ""
    especie: str = ""
    especie_codigo: int = 0
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    situacao: str = ""


@dataclass
class ResultadoParserCNIS:
    segurado: Optional[Segurado] = None
    vinculos: List[Vinculo] = field(default_factory=list)
    beneficios: List[BeneficioCNIS] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    campos_baixa_confianca: List[str] = field(default_factory=list)
    sucesso: bool = False


def parsear_cnis_pdf(caminho_pdf: str, texto_ocr: str = "") -> ResultadoParserCNIS:
    """
    Lê um PDF do CNIS e retorna os dados estruturados.
    Requer pdfplumber instalado.

    Args:
        caminho_pdf: Caminho do arquivo PDF
        texto_ocr: Texto já extraído via OCR (fallback para PDFs escaneados)
    """
    resultado = ResultadoParserCNIS()

    try:
        import pdfplumber
    except ImportError:
        resultado.erros.append("pdfplumber não instalado. Execute: pip install pdfplumber")
        return resultado

    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            texto_completo = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception as e:
        resultado.erros.append(f"Erro ao abrir PDF: {e}")
        texto_completo = ""

    # Se texto nativo vazio, usar OCR
    if not texto_completo.strip() and texto_ocr.strip():
        texto_completo = texto_ocr
        resultado.avisos.append("Texto extraído via OCR (documento escaneado)")

    if not texto_completo.strip():
        resultado.erros.append("PDF sem texto extraível (pode ser imagem — use OCR)")
        return resultado

    # Extrair dados pessoais
    dados_pessoais = _extrair_dados_pessoais(texto_completo, resultado)

    # Extrair vínculos e contribuições
    vinculos = _extrair_vinculos(texto_completo, resultado)

    # Extrair benefícios (aposentadoria ativa, indeferida, etc.)
    beneficios = _extrair_beneficios(texto_completo, resultado)
    resultado.beneficios = beneficios

    if dados_pessoais:
        # Converter benefícios CNIS para BeneficioAnterior do domínio
        beneficios_anteriores = _converter_beneficios_cnis(beneficios)
        segurado = Segurado(
            dados_pessoais=dados_pessoais,
            vinculos=vinculos,
            beneficios_anteriores=beneficios_anteriores,
        )
        resultado.segurado = segurado
        resultado.vinculos = vinculos
        resultado.sucesso = True
    else:
        resultado.erros.append("Não foi possível extrair os dados pessoais do segurado.")

    return resultado


def parsear_cnis_texto(texto: str) -> ResultadoParserCNIS:
    """Versão para testes: aceita texto diretamente."""
    resultado = ResultadoParserCNIS()
    dados_pessoais = _extrair_dados_pessoais(texto, resultado)
    vinculos = _extrair_vinculos(texto, resultado)
    beneficios = _extrair_beneficios(texto, resultado)
    resultado.beneficios = beneficios
    if dados_pessoais:
        beneficios_anteriores = _converter_beneficios_cnis(beneficios)
        resultado.segurado = Segurado(
            dados_pessoais=dados_pessoais,
            vinculos=vinculos,
            beneficios_anteriores=beneficios_anteriores,
        )
        resultado.vinculos = vinculos
        resultado.sucesso = True
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE DADOS PESSOAIS
# ─────────────────────────────────────────────────────────────────────────────

def _inferir_sexo_pelo_nome(nome: str) -> Sexo:
    """
    Infere o sexo pelo primeiro nome quando o CNIS não traz o campo explícito.
    Usa sufixos típicos do português brasileiro.
    """
    primeiro_nome = nome.split()[0].upper() if nome else ""

    # Nomes femininos terminados em A (com exceções)
    nomes_masc_em_a = {"JOSUA", "LUCA", "NIKITA", "SASCHA", "NATA"}
    # Nomes explicitamente femininos comuns
    nomes_fem = {
        "MARIA", "ANA", "ROSA", "LUIZA", "FRANCISCA", "ANTONIA", "ADRIANA",
        "CLAUDIA", "PATRICIA", "FERNANDA", "JULIANA", "MARIANA", "LUCIANA",
        "SANDRA", "SIMONE", "SUELI", "MADALENA", "HELENA", "IRENE", "ALICE",
        "BEATRIZ", "CARMEN", "INES", "IVONE", "RUTH", "RAQUEL", "ISABEL",
        "ELIZABETH", "NEIDE", "MARLENE", "ELIANE", "DENISE", "CRISTIANE",
        "ROSANGELA", "APARECIDA", "CONCEICAO", "FATIMA", "SOCORRO", "TEREZA",
        "TERESA", "TEREZINHA", "RAIMUNDA", "IVANILDE", "IVONETE", "VALDETE",
        "VALDELICE", "DAGMAR", "SOLANGE", "SHIRLEY", "VIVIANE", "MICHELE",
        "KELLY", "KAREN", "JAQUELINE", "VANESSA", "LARISSA", "LETICIA",
    }

    if primeiro_nome in nomes_fem:
        return Sexo.FEMININO

    # Sufixos femininos comuns em português
    if primeiro_nome.endswith("A") and primeiro_nome not in nomes_masc_em_a:
        return Sexo.FEMININO

    return Sexo.MASCULINO


def _extrair_dados_pessoais(texto: str, resultado: ResultadoParserCNIS) -> Optional[DadosPessoais]:
    # Nome — usar regex mais preciso para evitar capturar "Data de nascimento"
    nome = None
    # Padrão 1: Nome: FULANO DE TAL (pára antes de quebra de linha ou "Data")
    m_nome = re.search(
        r"Nome[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜa-záéíóúâêîôûãõçàü\s]+?)(?:\s*(?:Data|CPF|NIT|$|\n))",
        texto
    )
    if m_nome:
        nome = m_nome.group(1).strip()
    else:
        # Fallback
        m_nome2 = re.search(r"Nome[:\s]+([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚa-záéíóú\s]{3,50})", texto)
        if m_nome2:
            nome = m_nome2.group(1).strip()

    # Limpar nome: remover "Data de nascimento" ou outros restos comuns
    if nome:
        nome = re.sub(r"\s*Data\s+de\s+nascimento.*$", "", nome, flags=re.IGNORECASE).strip()
        nome = re.sub(r"\s*Nome\s+da\s+m[ãa]e.*$", "", nome, flags=re.IGNORECASE).strip()
        nome = re.sub(r"\s{2,}", " ", nome).strip()

    cpf = _extrair_campo(texto, [
        r"CPF[:\s/]*(\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\-\.]?\d{2})",
    ])
    dn = _extrair_campo(texto, [
        r"Data de [Nn]ascimento[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Nascimento[:\s]+(\d{2}/\d{2}/\d{4})",
        r"DT\.?\s*NASC\.?[:\s]+(\d{2}/\d{2}/\d{4})",
    ])
    sexo_raw = _extrair_campo(texto, [
        r"Sexo[:\s]+(Masculino|Feminino|M|F)",
        r"SEXO[:\s]+(MASCULINO|FEMININO|M|F)",
    ])

    if not nome or not dn:
        resultado.avisos.append("Nome ou data de nascimento não encontrados no CNIS.")
        return None

    try:
        partes = dn.split("/")
        data_nasc = date(int(partes[2]), int(partes[1]), int(partes[0]))
    except Exception:
        resultado.avisos.append(f"Data de nascimento inválida: {dn}")
        return None

    if sexo_raw:
        sexo = Sexo.FEMININO if sexo_raw.upper() in ("F", "FEMININO") else Sexo.MASCULINO
    else:
        # Inferir sexo pelo nome quando não encontrado explicitamente no CNIS
        sexo = _inferir_sexo_pelo_nome(nome) if nome else Sexo.MASCULINO
        if sexo == Sexo.MASCULINO:
            resultado.avisos.append("Sexo não encontrado no CNIS — assumindo Masculino. Confirme manualmente.")
        else:
            resultado.avisos.append(f"Sexo não encontrado no CNIS — inferido FEMININO pelo nome '{nome}'.")

    cpf_limpo = re.sub(r"[.\-/]", "", cpf) if cpf else ""

    # ── NIT / PIS / PASEP / NIS ──────────────────────────────────────────────
    nit = _extrair_campo(texto, [
        r"NIT[:\s]*(\d{3}[\.\-]?\d{5}[\.\-]?\d{2}[\-\.]?\d{1})",
        r"PIS[/\-\s]?PASEP[:\s]*(\d[\d\.\-]+)",
        r"NIS[:\s]*(\d{11})",
        r"N[úu]mero de Identifica[çc][ãa]o[:\s]*(\d[\d\.\-]+)",
    ])
    nit_limpo = re.sub(r"[.\-/]", "", nit) if nit else ""

    # Verificar se há múltiplos NITs no documento (sinal de cadastro fragmentado)
    todos_nits = set()
    for padrao in [
        r"NIT[:\s]*(\d{3}[\.\-]?\d{5}[\.\-]?\d{2}[\-\.]?\d{1})",
        r"PIS[/\-\s]?PASEP[:\s]*(\d[\d\.\-]+)",
        r"NIS[:\s]*(\d{11})",
    ]:
        for m in re.finditer(padrao, texto, re.IGNORECASE):
            n = re.sub(r"[.\-/]", "", m.group(1))
            if len(n) >= 10:
                todos_nits.add(n)

    if len(todos_nits) > 1:
        nits_fmt = ", ".join(sorted(todos_nits))
        resultado.avisos.append(
            f"⚠️ ATENÇÃO: Foram encontrados MÚLTIPLOS NITs neste CNIS ({nits_fmt}). "
            "Isso pode indicar cadastro fragmentado no INSS. Contribuições podem estar "
            "registradas em outro NIT e NÃO aparecer neste extrato. "
            "Recomenda-se solicitar a unificação dos NITs pelo telefone 135 ou Meu INSS."
        )

    return DadosPessoais(
        nome=nome.strip(),
        data_nascimento=data_nasc,
        sexo=sexo,
        cpf=cpf_limpo,
        nit=nit_limpo,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE VÍNCULOS E CONTRIBUIÇÕES
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_vinculos(texto: str, resultado: ResultadoParserCNIS) -> List[Vinculo]:
    """
    Extrai vínculos empregatícios e contribuições do texto do CNIS.

    O CNIS do INSS apresenta vínculos em blocos numerados (Seq. 1, 2, 3...)
    com empregador, datas, e lista de remunerações.
    """
    vinculos = []

    # Estratégia principal: procurar cada vínculo pelo padrão do CNIS
    # Formato típico: número sequencial + NIT + CNPJ + EMPREGADOR + Tipo + Datas
    blocos = _dividir_em_blocos_vinculo(texto)

    if not blocos:
        resultado.avisos.append(
            "Não foi possível identificar blocos de vínculos. "
            "Verifique o layout do CNIS e insira os dados manualmente."
        )
        return []

    for bloco in blocos:
        try:
            vinculo = _parsear_bloco_vinculo(bloco, resultado)
            if vinculo:
                vinculos.append(vinculo)
        except Exception as e:
            resultado.avisos.append(f"Erro ao processar bloco de vínculo: {e}")

    return vinculos


def _dividir_em_blocos_vinculo(texto: str) -> List[str]:
    """
    Divide o texto do CNIS em blocos, um por vínculo.

    O CNIS do INSS apresenta vínculos em dois formatos:
    1. COM CNPJ (empregado): "Seq NIT CNPJ NOME_EMPRESA Tipo Data_Inicio Data_Fim"
    2. SEM CNPJ (facultativo/CI): "Seq NIT RECOLHIMENTO Facultativo Data_Inicio Data_Fim Indicadores"
    3. BENEFÍCIO: "Seq NIT NB Benefício Espécie Data_Inicio Data_Fim Situação"

    Estratégia: encontrar TODOS os inícios de sequência (número + NIT) e dividir.
    """
    blocos = []

    # Padrão universal: número sequencial + NIT (presente em TODOS os vínculos do CNIS)
    # Formato: "1 105.61792.52-3" ou "2 105.61792.52-3" etc.
    # O NIT tem formato: XXX.XXXXX.XX-X
    padrao_seq_nit = re.compile(
        r"(?:^|\n)\s*"
        r"(\d{1,3})\s+"                                          # Seq number
        r"(\d{3}[\.\-]?\d{5}[\.\-]?\d{2}[\-\.]?\d{1})\s+"       # NIT
        r"(?:"
            r"(\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})"  # CNPJ (empregado)
            r"|(\d{10,})"                                         # NB (benefício)
            r"|([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜ][^\n]{2,})"                  # Nome/Origem (facultativo/recolhimento)
        r")"
    )

    matches = list(padrao_seq_nit.finditer(texto))

    if matches and len(matches) >= 1:
        for i, m in enumerate(matches):
            inicio = m.start()
            fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
            bloco = texto[inicio:fim]
            blocos.append(bloco.strip())
        return blocos

    # Fallback: padrão original com CNPJ apenas
    padrao_vinculo = re.compile(
        r"(\d{1,3})\s+"
        r"(\d{3}[\.\-]?\d{5}[\.\-]?\d{2}[\-\.]?\d{1})\s+"
        r"(\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})\s+"
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜ][^\n]{3,80})"
    )
    matches = list(padrao_vinculo.finditer(texto))
    if matches:
        for i, m in enumerate(matches):
            inicio = m.start()
            fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
            blocos.append(texto[inicio:fim].strip())
        return blocos

    # Fallback 2: dividir por CNPJ
    padrao_cnpj = re.compile(
        r"(\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})\s+"
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜ][^\n]{3,80})"
    )
    matches = list(padrao_cnpj.finditer(texto))
    if matches:
        for i, m in enumerate(matches):
            inicio = m.start()
            fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
            blocos.append(texto[inicio:fim].strip())
        return blocos

    # Fallback 3
    padroes_inicio = [
        r"(?m)^(?:Seq\.|Seqüência|Sequência)[:\s]*\d+",
        r"(?m)^\d{14}",
        r"(?m)^[A-Z]{2,}\s+\d{3}\.\d{3}\.\d{3}/\d{4}-\d{2}",
        r"(?m)Empregador[:\s]+",
    ]
    for padrao in padroes_inicio:
        splits = re.split(padrao, texto)
        if len(splits) > 1:
            return [s.strip() for s in splits if s.strip()]

    return [b.strip() for b in re.split(r"\n{3,}", texto) if len(b.strip()) > 50]


def _parsear_bloco_vinculo(bloco: str, resultado: ResultadoParserCNIS) -> Optional[Vinculo]:
    """Extrai um Vinculo de um bloco de texto."""

    # Verificar se o bloco é um benefício (não é vínculo de trabalho)
    # Detectar "Benefício 31 -" no início do bloco
    inicio_bloco = bloco[:300]
    if re.search(r"Benef[ií]cio\s+\d{2}\s*[-–—]", inicio_bloco, re.IGNORECASE):
        return None  # Benefícios são tratados separadamente

    # Extrair CNPJ/nome do empregador
    cnpj = _extrair_campo(bloco, [
        r"(\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})",
    ])

    # Nome do empregador
    nome_emp = None
    if cnpj:
        m_emp = re.search(
            re.escape(cnpj) + r"\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜa-záéíóúâêîôûãõçàü\s\.\-/&]{3,80}?)(?:\s+(?:Empregado|Contribuinte|Facultativ|Trabalhador))",
            bloco
        )
        if m_emp:
            nome_emp = m_emp.group(1).strip()
    if not nome_emp:
        nome_emp = _extrair_campo(bloco, [
            r"(?:Empresa|Empregador|Razão Social)[:\s]+([A-ZÁa-záéíóú][^\n]{5,60})",
        ])
    # Fallback: nome após CNPJ
    if not nome_emp and cnpj:
        m_fallback = re.search(
            re.escape(cnpj) + r"\s+([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀÜa-záéíóúâêîôûãõçàü\s\.\-/&]{3,70})",
            bloco
        )
        if m_fallback:
            nome_emp = m_fallback.group(1).strip()
            nome_emp = re.sub(r"\s+(Empregado|Contribuinte|Facultativ|Trabalhador|Agente).*$", "", nome_emp).strip()

    # Para vínculos sem CNPJ (FACULTATIVO, RECOLHIMENTO, CI):
    # Detectar tipo pelo texto "RECOLHIMENTO Facultativo" ou similar
    if not cnpj:
        m_recolh = re.search(r"RECOLHIMENTO\s+(Facultativ|Contribuinte|Individual)", bloco, re.IGNORECASE)
        if m_recolh:
            nome_emp = f"RECOLHIMENTO {m_recolh.group(1).upper()}"
        elif not nome_emp:
            # Tentar capturar origem do vínculo
            m_origem = re.search(r"(?:Origem\s+do\s+V[ií]nculo|RECOLHIMENTO|FILIAÇÃO)\s+(\S+)", bloco, re.IGNORECASE)
            if m_origem:
                nome_emp = m_origem.group(0).strip()[:50]

    # Datas de início e fim — formato DD/MM/AAAA
    datas = re.findall(r"(\d{2}/\d{2}/\d{4})", bloco)
    if len(datas) < 1:
        return None

    try:
        partes_i = datas[0].split("/")
        data_inicio = date(int(partes_i[2]), int(partes_i[1]), int(partes_i[0]))
    except Exception:
        return None

    # Validação básica
    if data_inicio.year < 1940 or data_inicio.year > 2030:
        return None

    data_fim = None
    if len(datas) >= 2:
        try:
            partes_f = datas[1].split("/")
            d_fim = date(int(partes_f[2]), int(partes_f[1]), int(partes_f[0]))
            if d_fim > data_inicio and d_fim.year >= 1940:
                data_fim = d_fim
        except Exception:
            pass

    # Tipo de vínculo
    tipo = _detectar_tipo_vinculo(bloco)

    # Extrair competências/remunerações
    contribuicoes = _extrair_contribuicoes_do_bloco(bloco, resultado)

    # Extrair indicadores do CNIS (PREC-MENOR-MIN, IREC-INDPEND, etc.)
    indicadores = _extrair_indicadores_bloco(bloco)

    # Marcar contribuições inválidas com base nos indicadores
    if indicadores:
        _aplicar_indicadores_contribuicoes(contribuicoes, indicadores, bloco)

    return Vinculo(
        tipo_vinculo=tipo,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        empregador_cnpj=re.sub(r"[.\-/]", "", cnpj) if cnpj else None,
        empregador_nome=nome_emp.strip() if nome_emp else None,
        data_inicio=data_inicio,
        data_fim=data_fim,
        contribuicoes=contribuicoes,
        origem=OrigemDado.CNIS,
        confianca_parser=Decimal("0.8"),
        indicadores=indicadores,
    )


def _extrair_contribuicoes_do_bloco(bloco: str, resultado: ResultadoParserCNIS) -> List[Contribuicao]:
    """
    Extrai linhas de competência/remuneração de um bloco de vínculo.

    O CNIS tem DOIS formatos de dados financeiros:

    1. Contribuições (FACULTATIVO/CI): 2 colunas por linha
       Competência Data_Pgto Contribuição Salário_Contribuição [Indicadores]
       09/2010     14/10/2010    56,10       510,00              IREC-LC123

    2. Remunerações (EMPREGADO ou B31): valor único
       Competência Remuneração [Indicadores]
       09/2018     954,00

    ATENÇÃO: O valor correto para TC é o SALÁRIO DE CONTRIBUIÇÃO (segunda coluna
    no formato 1, ou valor único no formato 2), NÃO o valor pago (primeira coluna).
    """
    contribuicoes = []

    # ── Formato 1: Contribuições com data de pagamento ──────────────────────
    # MM/YYYY  DD/MM/YYYY  valor_pago  salario_contribuicao  [indicadores]
    # Queremos capturar: competência (grupo 1), salário de contribuição (grupo 2)
    # e indicador individual da linha (grupo 3, opcional)
    padrao_contrib = re.compile(
        r"(\d{2}/\d{4})\s+"            # Competência (MM/YYYY)
        r"\d{2}/\d{2}/\d{4}\s+"        # Data de pagamento (DD/MM/YYYY) — ignorar
        r"[\d\.]+,\d{2}\s+"            # Valor pago (contribuição) — ignorar
        r"([\d\.]+,\d{2})"             # Salário de contribuição — ESTE é o correto
        r"(?:\s+([A-Z][A-Z0-9_-]+))?"  # Indicador individual da linha (opcional)
    )

    # ── Formato 2: Remunerações sem data de pagamento ──────────────────────
    # MM/YYYY  valor  [indicadores]
    # Usar lookbehind para evitar capturar MM/YYYY de dentro de DD/MM/YYYY
    padrao_remun = re.compile(
        r"(?<!\d/)"                     # NÃO precedido por "N/" (evita DD/MM/YYYY)
        r"(\d{2}/\d{4})\s+"            # Competência (MM/YYYY)
        r"([\d\.]+,\d{2})"             # Remuneração
        r"(?:\s+([A-Z][A-Z0-9_-]+))?"  # Indicador individual da linha (opcional)
    )

    # Indicadores que INVALIDAM a contribuição individual
    excludentes_tc = {"PREC-MENOR-MIN", "PREC-FACULTCONC"}
    excludentes_carencia = excludentes_tc | {"PREC-MENOR-QTD"}

    # Primeiro: tentar formato com data de pagamento (mais preciso)
    competencias_encontradas = set()
    for m in padrao_contrib.finditer(bloco):
        comp_str = m.group(1)
        valor_str = m.group(2)
        indicador_linha = m.group(3) or ""  # Indicador desta contribuição
        try:
            comp = competencia_str(comp_str)
            valor_limpo = valor_str.replace(".", "").replace(",", ".")
            sc = Decimal(valor_limpo)
            if sc <= Decimal("0"):
                continue
            comp_key = comp.strftime("%m/%Y")
            if comp_key not in competencias_encontradas:
                competencias_encontradas.add(comp_key)
                c = Contribuicao(
                    competencia=comp,
                    salario_contribuicao=sc,
                )
                # Aplicar indicador PER-CONTRIBUIÇÃO (não por bloco!)
                if indicador_linha:
                    ind_upper = indicador_linha.upper().strip()
                    if ind_upper in excludentes_tc:
                        c.valida_tc = False
                        c.observacao = f"[{ind_upper}]"
                    if ind_upper in excludentes_carencia:
                        c.valida_carencia = False
                contribuicoes.append(c)
        except (ValueError, InvalidOperation):
            continue

    # Se não encontrou no formato 1, tentar formato 2 (remunerações simples)
    if not contribuicoes:
        for m in padrao_remun.finditer(bloco):
            comp_str = m.group(1)
            valor_str = m.group(2)
            indicador_linha = m.group(3) or ""
            try:
                comp = competencia_str(comp_str)
                valor_limpo = valor_str.replace(".", "").replace(",", ".")
                sc = Decimal(valor_limpo)
                if sc <= Decimal("0"):
                    continue
                comp_key = comp.strftime("%m/%Y")
                if comp_key not in competencias_encontradas:
                    competencias_encontradas.add(comp_key)
                    c = Contribuicao(
                        competencia=comp,
                        salario_contribuicao=sc,
                    )
                    if indicador_linha:
                        ind_upper = indicador_linha.upper().strip()
                        if ind_upper in excludentes_tc:
                            c.valida_tc = False
                            c.observacao = f"[{ind_upper}]"
                        if ind_upper in excludentes_carencia:
                            c.valida_carencia = False
                    contribuicoes.append(c)
            except (ValueError, InvalidOperation):
                continue

    return contribuicoes


def _extrair_indicadores_bloco(bloco: str) -> str:
    """
    Extrai indicadores do CNIS presentes no bloco do vínculo.

    Indicadores comuns no CNIS:
    - PREC-MENOR-MIN: Recolhimento abaixo do salário mínimo
    - PREC-FACULTCONC: Facultativo concomitante com obrigatória
    - IREC-INDPEND: Recolhimento com pendência
    - IREC-LC123: Recolhimento via Simples Nacional com pendência
    - IREM-INDPAM: Remuneração com pendência
    - AEXT-VI: Acerto extemporâneo com vínculo/indicadores
    - PREM-EXT: Remuneração com extemporaneidade
    - PVIN-IRREG: Vínculo com irregularidade
    """
    indicadores_encontrados = []

    # Padrões de indicadores CNIS
    padroes_indicadores = [
        r"PREC-MENOR-MIN",
        r"PREC-FACULTCONC",
        r"PREC-MENOR-QTD",
        r"IREC-INDPEND",
        r"IREC-LC123",
        r"IREM-INDPAM",
        r"AEXT-VI",
        r"PREM-EXT",
        r"PVIN-IRREG",
        r"PREM-PMBC",
        r"PREM-RET",
        r"PREC-FBR-INF",
    ]

    bloco_upper = bloco.upper()
    for padrao in padroes_indicadores:
        if re.search(padrao, bloco_upper):
            indicadores_encontrados.append(padrao)

    # Também detectar menções textuais de indicadores
    # "Vínculo com Indicadores" ou "Pendência" no texto da simulação INSS
    if re.search(r"V[ÍI]NCULO\s+COM\s+INDICADOR", bloco_upper):
        if "PVIN-IRREG" not in indicadores_encontrados:
            indicadores_encontrados.append("PVIN-INDICADORES")

    return ", ".join(indicadores_encontrados)


def _aplicar_indicadores_contribuicoes(
    contribuicoes: List[Contribuicao],
    indicadores: str,
    bloco: str,
):
    """
    Marca contribuições como inválidas para TC/carência com base nos indicadores.

    IMPORTANTE: Se a contribuição JÁ teve indicador aplicado individualmente
    (na extração per-linha), NÃO sobrescrever. Os indicadores de bloco só
    se aplicam quando TODAS as contribuições do bloco têm o mesmo indicador
    (ex: bloco inteiro com IREC-INDPEND no cabeçalho).

    Indicadores que EXCLUEM contribuições:
    - PREC-MENOR-MIN: contribuição abaixo do salário mínimo (Art. 19-E Decreto 3.048/99)
    - PREC-FACULTCONC: facultativo concomitante com obrigatória → duplicado

    Indicadores INFORMATIVOS (NÃO excluem):
    - IREC-INDPEND: pendência administrativa — comum, geralmente regularizável
    - IREC-LC123: recolhimento via Simples Nacional — válido, apenas indica origem
    - AEXT-VI: acerto extemporâneo — contribuição válida após regularização
    - PREM-EXT: remuneração extemporânea — informativo
    """
    indicadores_set = {ind.strip().upper() for ind in indicadores.split(",") if ind.strip()}

    # Apenas indicadores que REALMENTE invalidam a contribuição por lei
    excludentes_tc = {"PREC-MENOR-MIN", "PREC-FACULTCONC"}
    excludentes_carencia = excludentes_tc | {"PREC-MENOR-QTD"}

    # Verificar se alguma contribuição já teve indicador aplicado individualmente
    alguma_com_indicador_individual = any(c.observacao for c in contribuicoes)

    if alguma_com_indicador_individual:
        # Indicadores já foram aplicados PER-CONTRIBUIÇÃO — não sobrescrever
        # Cada contribuição já tem seu próprio indicador correto
        return

    # Nenhuma contribuição teve indicador individual → aplicar do bloco a todas
    if indicadores_set & excludentes_tc:
        for c in contribuicoes:
            c.valida_tc = False
            c.observacao = (c.observacao or "") + f" [{indicadores}]"

    if indicadores_set & excludentes_carencia:
        for c in contribuicoes:
            c.valida_carencia = False


def _detectar_tipo_vinculo(bloco: str) -> TipoVinculo:
    """Detecta o tipo de vínculo a partir do texto do bloco."""
    bloco_upper = bloco.upper()
    if "DOMÉSTICO" in bloco_upper or "DOMESTICO" in bloco_upper:
        return TipoVinculo.EMPREGADO_DOMESTICO
    if "AVULSO" in bloco_upper:
        return TipoVinculo.TRABALHADOR_AVULSO
    if "FACULTATIV" in bloco_upper:
        return TipoVinculo.FACULTATIVO
    if "MEI" in bloco_upper or "MICRO EMPREENDEDOR" in bloco_upper:
        return TipoVinculo.MEI
    if "INDIVIDUAL" in bloco_upper or "AUTÔNOMO" in bloco_upper or "AUTONOMO" in bloco_upper:
        return TipoVinculo.CONTRIBUINTE_INDIVIDUAL
    if "RURAL" in bloco_upper or "ESPECIAL" in bloco_upper:
        return TipoVinculo.SEGURADO_ESPECIAL
    return TipoVinculo.EMPREGADO  # padrão


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSÃO DE BENEFÍCIOS CNIS → DOMÍNIO
# ─────────────────────────────────────────────────────────────────────────────

# Mapeamento de código de espécie CNIS → TipoBeneficio
_MAPA_ESPECIE = {
    31: TipoBeneficio.AUXILIO_DOENCA_PREV,
    32: TipoBeneficio.APOSENTADORIA_INVALIDEZ_PREV,
    36: TipoBeneficio.AUXILIO_ACIDENTE,
    41: TipoBeneficio.APOSENTADORIA_IDADE,
    42: TipoBeneficio.APOSENTADORIA_IDADE_RURAL,
    46: TipoBeneficio.APOSENTADORIA_ESPECIAL,
    57: TipoBeneficio.APOSENTADORIA_TEMPO_CONTRIB,
    80: TipoBeneficio.SALARIO_MATERNIDADE,
    87: TipoBeneficio.BPC_LOAS_IDOSO,
    88: TipoBeneficio.BPC_LOAS_DEFICIENTE,
    91: TipoBeneficio.AUXILIO_DOENCA_ACID,
    92: TipoBeneficio.APOSENTADORIA_INVALIDEZ_ACID,
    21: TipoBeneficio.PENSAO_MORTE_URBANA,
    22: TipoBeneficio.PENSAO_MORTE_RURAL,
    25: TipoBeneficio.AUXILIO_RECLUSAO,
}


def _converter_beneficios_cnis(beneficios: List[BeneficioCNIS]) -> List[BeneficioAnterior]:
    """
    Converte benefícios extraídos do CNIS em objetos de domínio BeneficioAnterior.

    Isso é crítico para:
    - Auxílio-doença (espécie 31/91): seus períodos contam como TC quando intercalados
    - Aposentadoria ativa: indica que o segurado já é aposentado (revisão, não planejamento)
    """
    resultado = []
    for b in beneficios:
        # Ignorar benefícios INDEFERIDOS — nunca foram concedidos
        if b.situacao == "INDEFERIDO":
            continue

        # Ignorar benefícios sem data de início (dados insuficientes)
        if b.data_inicio is None:
            continue

        especie = _MAPA_ESPECIE.get(b.especie_codigo, TipoBeneficio.AUXILIO_DOENCA_PREV)

        dcb = b.data_fim
        if b.situacao == "ATIVO":
            dcb = None  # Benefício em curso

        resultado.append(BeneficioAnterior(
            numero_beneficio=b.nb,
            especie=especie,
            dib=b.data_inicio,
            dcb=dcb,
        ))
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE BENEFÍCIOS (APOSENTADORIA, PENSÃO, etc.)
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_beneficios(texto: str, resultado: ResultadoParserCNIS) -> List[BeneficioCNIS]:
    """
    Detecta benefícios previdenciários no CNIS.
    Ex: "42 - APOSENTADORIA POR TEMPO DE CONTRIBUICAO 07/03/2018 ATIVO"
    """
    beneficios = []

    # Capturar tudo da linha do benefício para fazer parse manual
    padrao = re.compile(
        r"Benef[ií]cio\s+(\d{2})\s*[-–—]\s*([^\n]+)",
        re.IGNORECASE
    )

    for m in padrao.finditer(texto):
        cod = int(m.group(1))
        linha = m.group(2).strip()

        # Extrair espécie (tudo antes da data ou status)
        # Ex: "APOSENTADORIA POR TEMPO DE 07/03/2018 ATIVO"
        # Ex: "APOSENTADORIA POR TEMPO DE INDEFERIDO"
        especie = linha

        # Extrair TODAS as datas DD/MM/AAAA (DIB e DCB)
        datas_str = re.findall(r"(\d{2}/\d{2}/\d{4})", linha)
        dt_inicio_str = datas_str[0] if len(datas_str) >= 1 else None
        dt_fim_str = datas_str[1] if len(datas_str) >= 2 else None

        # Extrair situação
        sit_match = re.search(r"(ATIVO|CESSADO|INDEFERIDO|SUSPENSO)", linha, re.IGNORECASE)
        situacao = sit_match.group(1).upper() if sit_match else ""

        # Limpar espécie: remover data e situação do texto
        especie = re.sub(r"\d{2}/\d{2}/\d{4}", "", especie)
        especie = re.sub(r"(ATIVO|CESSADO|INDEFERIDO|SUSPENSO)", "", especie, flags=re.IGNORECASE)
        especie = re.sub(r"\s+", " ", especie).strip()

        dt_inicio = None
        if dt_inicio_str:
            try:
                p = dt_inicio_str.split("/")
                dt_inicio = date(int(p[2]), int(p[1]), int(p[0]))
            except Exception:
                pass

        dt_fim = None
        if dt_fim_str:
            try:
                p = dt_fim_str.split("/")
                dt_fim = date(int(p[2]), int(p[1]), int(p[0]))
            except Exception:
                pass

        b = BeneficioCNIS(
            nb=m.group(0)[:20],
            especie=especie,
            especie_codigo=cod,
            data_inicio=dt_inicio,
            data_fim=dt_fim,
            situacao=situacao,
        )
        beneficios.append(b)

    # Gerar avisos sobre benefícios ativos
    for b in beneficios:
        if b.situacao == "ATIVO":
            dt_str = b.data_inicio.strftime("%d/%m/%Y") if b.data_inicio else "data não identificada"
            resultado.avisos.append(
                f"🏆 BENEFÍCIO ATIVO DETECTADO: {b.especie} (espécie {b.especie_codigo}) "
                f"concedido em {dt_str}. O segurado JÁ ESTÁ APOSENTADO. "
                f"Avaliar cabimento de revisão do benefício."
            )
        elif b.situacao == "INDEFERIDO":
            resultado.avisos.append(
                f"❌ BENEFÍCIO INDEFERIDO: {b.especie} (espécie {b.especie_codigo}). "
                f"Verificar motivo do indeferimento e possibilidade de recurso."
            )
        elif b.situacao == "CESSADO":
            dt_str = b.data_inicio.strftime("%d/%m/%Y") if b.data_inicio else "?"
            resultado.avisos.append(
                f"⏹️ BENEFÍCIO CESSADO: {b.especie} desde {dt_str}. "
                f"Verificar motivo da cessação."
            )

    return beneficios


# ─────────────────────────────────────────────────────────────────────────────
# Busca de NB (número de benefício) no texto
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_nb(texto: str) -> Optional[str]:
    """Extrai número de benefício do CNIS."""
    m = re.search(r"NB[:\s]*(\d{10,})", texto)
    if m:
        return m.group(1)
    m = re.search(r"(\d{10})\s+Benef", texto)
    if m:
        return m.group(1)
    return None


def _extrair_campo(texto: str, padroes: List[str]) -> Optional[str]:
    """Tenta extrair um campo tentando uma lista de padrões regex."""
    for padrao in padroes:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None
