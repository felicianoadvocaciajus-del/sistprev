"""
Parser de PPP (Perfil Profissografico Previdenciario).

Extrai dados do PPP em PDF (digital ou escaneado via OCR):
- Dados do trabalhador (nome, CPF, NIT)
- Dados da empresa (razao social, CNPJ, CNAE, grau de risco)
- Cargo, CBO, setor
- Periodos de exposicao a agentes nocivos (o mais importante!)
- Intensidade, EPI/EPC eficaz
- Responsaveis tecnicos

O PPP e o documento CHAVE para comprovar atividade especial.
Formulario padronizado conforme IN INSS/PRES 128/2022 e Decreto 3.048/99.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
import re
import logging

logger = logging.getLogger("sistprev.parser.ppp")


@dataclass
class ExposicaoAgente:
    """Um periodo de exposicao a agente nocivo extraido do PPP."""
    agente_nocivo: Optional[str] = None
    codigo_agente: Optional[str] = None        # Ex: "2.0.1" (ruido)
    intensidade: Optional[str] = None           # Ex: "92 dB(A)"
    tecnica_avaliacao: Optional[str] = None     # Quantitativa/Qualitativa
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    epc_eficaz: Optional[bool] = None           # Sim/Nao
    epi_eficaz: Optional[bool] = None           # Sim/Nao
    ca_epi: Optional[str] = None                # Certificado de Aprovacao
    setor: Optional[str] = None
    cargo: Optional[str] = None


@dataclass
class ResultadoParserPPP:
    """Resultado do parsing de um PPP."""
    sucesso: bool = False
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    # Dados do trabalhador
    nome: Optional[str] = None
    cpf: Optional[str] = None
    nit: Optional[str] = None
    data_nascimento: Optional[date] = None
    sexo: Optional[str] = None
    # Dados da empresa
    empresa_razao_social: Optional[str] = None
    empresa_cnpj: Optional[str] = None
    empresa_cnae: Optional[str] = None
    empresa_grau_risco: Optional[str] = None
    # Vinculo
    cargo: Optional[str] = None
    cbo: Optional[str] = None
    setor: Optional[str] = None
    data_admissao: Optional[date] = None
    data_demissao: Optional[date] = None
    # Exposicoes (a parte mais importante)
    exposicoes: List[ExposicaoAgente] = field(default_factory=list)
    # Responsaveis
    responsavel_registros: Optional[str] = None
    responsavel_crm_crea: Optional[str] = None
    data_emissao: Optional[date] = None
    # Texto bruto (para debug)
    texto_bruto: str = ""


def parsear_ppp_pdf(caminho_pdf: str, texto_ocr: str = "") -> ResultadoParserPPP:
    """
    Parseia um PPP em PDF (digital ou escaneado).

    Args:
        caminho_pdf: Caminho do arquivo PDF
        texto_ocr: Texto ja extraido via OCR (opcional, usado como fallback)
    """
    resultado = ResultadoParserPPP()

    # Tentar extrair texto nativo
    texto = ""
    try:
        import pdfplumber
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                texto += t + "\n"
    except Exception as e:
        resultado.avisos.append(f"Erro ao ler PDF nativo: {e}")

    # Se texto nativo vazio, usar OCR
    if not texto.strip() and texto_ocr.strip():
        texto = texto_ocr
        resultado.avisos.append("Texto extraido via OCR (documento escaneado)")
    elif not texto.strip() and not texto_ocr.strip():
        resultado.erros.append("Nao foi possivel extrair texto do PPP")
        return resultado

    return _parsear_texto_ppp(texto, resultado)


def parsear_ppp_texto(texto: str) -> ResultadoParserPPP:
    """Parseia PPP a partir de texto puro."""
    return _parsear_texto_ppp(texto, ResultadoParserPPP())


def _parsear_texto_ppp(texto: str, resultado: ResultadoParserPPP) -> ResultadoParserPPP:
    """Logica principal de extracao do PPP."""
    resultado.texto_bruto = texto
    texto_upper = texto.upper()

    # ── DADOS DO TRABALHADOR ──────────────────────────────────────────────
    resultado.nome = _campo(texto, [
        r'(?:NOME\s*(?:DO\s*)?TRABALHADOR|NOME\s*COMPLETO)\s*[:\-]?\s*([A-Z\s\u00C0-\u00FF]{5,60})',
    ])

    cpf_match = _campo(texto, [
        r'(?:CPF|C\.?P\.?F\.?)\s*[:\-]?\s*(\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[\.\s\-]?\d{2})',
    ])
    if cpf_match:
        resultado.cpf = re.sub(r'\D', '', cpf_match)

    nit_match = _campo(texto, [
        r'(?:NIT|PIS|PASEP|NIT/PIS/PASEP)\s*[:\-]?\s*(\d{3}[\.\s]?\d{5}[\.\s]?\d{2}[\.\s\-]?\d{1})',
        r'(?:NIT|PIS|PASEP)\s*[:\-]?\s*(\d{11})',
    ])
    if nit_match:
        resultado.nit = re.sub(r'\D', '', nit_match)

    resultado.data_nascimento = _parse_data(_campo(texto, [
        r'(?:DATA\s*(?:DE\s*)?NASCIMENTO|NASC\.?)\s*[:\-]?\s*(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})',
    ]), resultado, "data_nascimento")

    sexo = _campo(texto_upper, [
        r'SEXO\s*[:\-]?\s*(MASCULINO|FEMININO|M|F)',
    ])
    if sexo:
        resultado.sexo = "MASCULINO" if sexo.startswith("M") else "FEMININO"

    # ── DADOS DA EMPRESA ──────────────────────────────────────────────────
    resultado.empresa_razao_social = _campo(texto, [
        r'(?:RAZ[AÃ]O\s*SOCIAL|NOME\s*(?:DA\s*)?EMPRESA|EMPREGADOR)\s*[:\-]?\s*(.{5,80})',
    ])

    cnpj_match = _campo(texto, [
        r'(?:CNPJ|C\.?N\.?P\.?J\.?)\s*[:\-]?\s*(\d{2}[\.\s]?\d{3}[\.\s]?\d{3}[/\s]?\d{4}[\.\s\-]?\d{2})',
        r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
    ])
    if cnpj_match:
        resultado.empresa_cnpj = re.sub(r'[^\d/\-\.]', '', cnpj_match)

    resultado.empresa_cnae = _campo(texto, [
        r'(?:CNAE|C\.?N\.?A\.?E\.?)\s*[:\-]?\s*(\d{4}[\-\.]?\d[\-/]?\d{2})',
        r'(?:CNAE|C\.?N\.?A\.?E\.?)\s*[:\-]?\s*(\d{5,7})',
    ])

    grau = _campo(texto, [
        r'(?:GRAU\s*(?:DE\s*)?RISCO)\s*[:\-]?\s*(\d)',
    ])
    if grau:
        resultado.empresa_grau_risco = grau

    # ── CARGO / CBO / SETOR ──────────────────────────────────────────────
    resultado.cargo = _campo(texto, [
        r'(?:CARGO|FUN[CÇ][AÃ]O|ATIVIDADE)\s*[:\-]?\s*([A-Z\s\u00C0-\u00FF/\-]{3,60})',
    ])

    resultado.cbo = _campo(texto, [
        r'(?:CBO|C\.?B\.?O\.?)\s*[:\-]?\s*(\d{4,6}[\-\.]?\d{0,2})',
        r'(?:COD\.?\s*CBO|CODIGO\s*CBO)\s*[:\-]?\s*(\d{4,6})',
    ])

    resultado.setor = _campo(texto, [
        r'(?:SETOR|LOCAL\s*(?:DE\s*)?TRABALHO|DESCRI[CÇ][AÃ]O\s*DO\s*LOCAL)\s*[:\-]?\s*(.{3,80})',
    ])

    # ── DATAS DO VINCULO ─────────────────────────────────────────────────
    resultado.data_admissao = _parse_data(_campo(texto, [
        r'(?:DATA\s*(?:DE\s*)?ADMISS[AÃ]O|ADMISS[AÃ]O)\s*[:\-]?\s*(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})',
    ]), resultado, "data_admissao")

    resultado.data_demissao = _parse_data(_campo(texto, [
        r'(?:DATA\s*(?:DE\s*)?(?:DESLIGAMENTO|DEMISS[AÃ]O|SA[IÍ]DA))\s*[:\-]?\s*(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})',
    ]), resultado, "data_demissao")

    # ── EXPOSICOES A AGENTES NOCIVOS (A PARTE MAIS IMPORTANTE) ───────────
    _extrair_exposicoes(texto, resultado)

    # ── RESPONSAVEIS ─────────────────────────────────────────────────────
    resultado.responsavel_registros = _campo(texto, [
        r'(?:RESPONS[AÁ]VEL\s*(?:PELOS?\s*)?REGISTROS?\s*AMBIENTAIS?|ENG\.?\s*SEGURAN[CÇ]A|T[EÉ]C\.?\s*SEGURAN[CÇ]A)\s*[:\-]?\s*([A-Z\s\u00C0-\u00FF\.]{5,60})',
    ])

    resultado.responsavel_crm_crea = _campo(texto, [
        r'(?:CRM|CREA|CRF|REGISTRO\s*PROFISSIONAL)\s*[:\-/]?\s*([\w\.\-/\s]{3,30})',
    ])

    resultado.data_emissao = _parse_data(_campo(texto, [
        r'(?:DATA\s*(?:DE\s*)?EMISS[AÃ]O|EMITIDO\s*EM|DATA\s*DO\s*PPP)\s*[:\-]?\s*(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})',
    ]), resultado, "data_emissao")

    # ── VALIDACAO ────────────────────────────────────────────────────────
    campos_encontrados = sum(1 for x in [
        resultado.nome, resultado.cpf, resultado.empresa_cnpj,
        resultado.cargo, resultado.empresa_razao_social,
    ] if x)

    if campos_encontrados == 0 and not resultado.exposicoes:
        resultado.erros.append("Nao foi possivel extrair dados do PPP. Verifique se o documento e um PPP valido.")
    else:
        resultado.sucesso = True
        if campos_encontrados < 3:
            resultado.avisos.append(f"Apenas {campos_encontrados} campos identificados. Documento pode estar parcialmente ilegivel.")
        if resultado.exposicoes:
            resultado.avisos.append(f"{len(resultado.exposicoes)} exposicao(oes) a agente(s) nocivo(s) identificada(s)")
        else:
            resultado.avisos.append("Nenhuma exposicao a agente nocivo encontrada no PPP")

    return resultado


def _extrair_exposicoes(texto: str, resultado: ResultadoParserPPP):
    """Extrai periodos de exposicao a agentes nocivos do PPP."""
    texto_upper = texto.upper()

    # Padroes de agentes nocivos conhecidos
    AGENTES_CONHECIDOS = {
        r'RU[IÍ]DO': 'RUIDO',
        r'VIBRA[CÇ][AÃ]O': 'VIBRACAO',
        r'CALOR': 'CALOR',
        r'FRIO': 'FRIO',
        r'RADIA[CÇ][AÃ]O': 'RADIACAO',
        r'PRESS[AÃ]O\s*ATMOSF': 'PRESSAO',
        r'ELETRICIDADE|TENS[AÃ]O\s*EL[EÉ]TRICA': 'ELETRICIDADE',
        r'POEIRA|PART[IÍ]CULAS': 'POEIRA',
        r'S[IÍ]LICA': 'SILICA',
        r'AMIANTO|ASBESTO': 'AMIANTO',
        r'BENZENO': 'BENZENO',
        r'TOLUENO': 'TOLUENO',
        r'XILENO': 'XILENO',
        r'HIDROCARBONETO': 'HIDROCARBONETOS',
        r'SOLVENTE': 'SOLVENTES',
        r'CHUMBO': 'CHUMBO',
        r'CROMO|CR[OÔ]MIO': 'CROMO',
        r'MERC[UÚ]RIO': 'MERCURIO',
        r'AGENTE\s*BIOL[OÓ]GICO|MICRO[\-\s]?ORGANISMO|V[IÍ]RUS|BACT[EÉ]RIA': 'AGENTES_BIOLOGICOS',
        r'[OÓ]LEO\s*MINERAL': 'OLEO_MINERAL',
        r'COMBUST[IÍ]VEL|GASOLINA|DIESEL|[AÁ]LCOOL': 'COMBUSTIVEIS',
        r'SOLDA|FUMO\s*MET[AÁ]LICO': 'FUMOS_METALICOS',
        r'PERICULOSIDADE|ARMA\s*(?:DE\s*)?FOGO|INFLAM[AÁ]VEL|EXPLOSIVO': 'PERICULOSIDADE',
        r'CLORO': 'CLORO',
        r'[AÁ]CIDO': 'ACIDOS',
    }

    # Buscar cada agente no texto
    agentes_encontrados = []
    for padrao, codigo in AGENTES_CONHECIDOS.items():
        matches = list(re.finditer(padrao, texto_upper))
        if matches:
            agentes_encontrados.append((codigo, matches[0].start(), matches[0].group()))

    # Buscar intensidades (ex: "92 dB(A)", "0,8 mg/m3")
    intensidades = re.findall(
        r'(\d+[\.,]?\d*)\s*(dB\s*\(?A?\)?|mg/m[³3]|ppm|mW/cm[²2]|lux|[°º]C|m/s[²2])',
        texto, re.IGNORECASE
    )

    # Buscar periodos de exposicao
    periodos = re.findall(
        r'(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})\s*(?:a|at[eé]|[-–])\s*(\d{2}[/\.\-]\d{2}[/\.\-]\d{4})',
        texto, re.IGNORECASE
    )

    # Buscar codigos do Anexo IV do Decreto 3.048
    codigos_anexo = re.findall(
        r'(?:C[OÓ]DIGO|ANEXO\s*IV|DEC\.?\s*3\.?048)\s*[:\-]?\s*(\d{1,2}\.\d{1,2}\.?\d{0,2})',
        texto, re.IGNORECASE
    )

    # Buscar EPI/EPC eficaz
    epi_eficaz = None
    epc_eficaz = None
    epi_match = re.search(r'EPI\s*(?:EFICAZ|EFIC\.?)?\s*[:\-]?\s*(SIM|S|N[AÃ]O|N)\b', texto_upper)
    if epi_match:
        epi_eficaz = epi_match.group(1).startswith('S')
    epc_match = re.search(r'EPC\s*(?:EFICAZ|EFIC\.?)?\s*[:\-]?\s*(SIM|S|N[AÃ]O|N)\b', texto_upper)
    if epc_match:
        epc_eficaz = epc_match.group(1).startswith('S')

    # Buscar CA do EPI
    ca_epi = _campo(texto, [
        r'(?:CA|C\.?A\.?)\s*(?:N[°ºo\.]*|:)\s*(\d{3,6})',
    ])

    # Criar exposicoes
    if agentes_encontrados:
        for codigo, pos, match_text in agentes_encontrados:
            exp = ExposicaoAgente(
                agente_nocivo=codigo,
                epi_eficaz=epi_eficaz,
                epc_eficaz=epc_eficaz,
                ca_epi=ca_epi,
                cargo=resultado.cargo,
                setor=resultado.setor,
            )

            # Associar intensidade mais proxima
            if intensidades:
                exp.intensidade = f"{intensidades[0][0]} {intensidades[0][1]}"

            # Associar codigo do Anexo IV
            if codigos_anexo:
                exp.codigo_agente = codigos_anexo[0]

            # Associar periodo
            if periodos:
                exp.data_inicio = _parse_data_simples(periodos[0][0])
                exp.data_fim = _parse_data_simples(periodos[0][1])
            elif resultado.data_admissao:
                exp.data_inicio = resultado.data_admissao
                exp.data_fim = resultado.data_demissao

            resultado.exposicoes.append(exp)
    elif intensidades:
        # Tem intensidade mas nao identificou o agente especifico
        exp = ExposicaoAgente(
            agente_nocivo="AGENTE_NAO_IDENTIFICADO",
            intensidade=f"{intensidades[0][0]} {intensidades[0][1]}",
            epi_eficaz=epi_eficaz,
            epc_eficaz=epc_eficaz,
            cargo=resultado.cargo,
            setor=resultado.setor,
        )
        if periodos:
            exp.data_inicio = _parse_data_simples(periodos[0][0])
            exp.data_fim = _parse_data_simples(periodos[0][1])
        resultado.exposicoes.append(exp)
        resultado.avisos.append("Intensidade detectada mas agente nocivo nao identificado claramente")


def _campo(texto: str, padroes: list) -> Optional[str]:
    """Tenta cada padrao regex e retorna o primeiro match."""
    for padrao in padroes:
        m = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def _parse_data(s: Optional[str], resultado: ResultadoParserPPP, nome: str) -> Optional[date]:
    """Converte string DD/MM/YYYY para date."""
    if not s:
        return None
    return _parse_data_simples(s)


def _parse_data_simples(s: str) -> Optional[date]:
    """Converte string DD/MM/YYYY para date, sem log."""
    if not s:
        return None
    s = s.replace('.', '/').replace('-', '/')
    try:
        partes = s.split('/')
        if len(partes) == 3:
            d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
            if a < 100:
                a += 2000 if a < 50 else 1900
            return date(a, m, d)
    except (ValueError, IndexError):
        pass
    return None
