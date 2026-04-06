"""
Parser da Carta de Concessão do INSS em PDF.

A Carta de Concessão é o documento emitido pelo INSS ao deferir um benefício.
Contém: número do benefício (NB), espécie (tipo), DIB, DIP, RMI, competência
de início de pagamento, dados do beneficiário e fundamentação legal.

Layout padrão do documento INSS (SIRC/PLENUS):
  - Cabeçalho: INSS + unidade de pagamento
  - Dados do segurado: nome, CPF, NIT
  - Dados do benefício: NB, espécie, DIB, DIP, RMI, DCB (se cessado)
  - Composição do salário de benefício (quando presente)
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class DadosBeneficio:
    numero_beneficio: Optional[str] = None       # NB — 10 dígitos
    especie: Optional[str] = None                # ex: "41", "42", "46", "57"
    descricao_especie: Optional[str] = None      # ex: "Aposentadoria por Tempo de Contribuição"
    dib: Optional[date] = None                   # Data de Início do Benefício
    dip: Optional[date] = None                   # Data de Início do Pagamento
    dcb: Optional[date] = None                   # Data de Cessação (se houver)
    rmi: Optional[Decimal] = None                # Renda Mensal Inicial
    salario_beneficio: Optional[Decimal] = None  # SB antes de limitação ao teto
    fator_previdenciario: Optional[Decimal] = None
    coeficiente: Optional[Decimal] = None
    competencia_inicio_pagamento: Optional[str] = None
    nome_segurado: Optional[str] = None
    cpf: Optional[str] = None
    nit: Optional[str] = None


@dataclass
class ResultadoParserCarta:
    beneficio: Optional[DadosBeneficio] = None
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    sucesso: bool = False


def parsear_carta_concessao(caminho_pdf: str, texto_ocr: str = "") -> ResultadoParserCarta:
    """
    Lê uma Carta de Concessão do INSS em PDF e extrai os dados estruturados.

    Args:
        caminho_pdf: Caminho do arquivo PDF
        texto_ocr: Texto já extraído via OCR (se disponível). Quando fornecido,
                   é usado como fallback se o texto nativo estiver vazio.
    """
    resultado = ResultadoParserCarta()

    try:
        import pdfplumber
    except ImportError:
        resultado.erros.append("pdfplumber não instalado. Execute: pip install pdfplumber")
        return resultado

    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            texto = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        resultado.erros.append(f"Erro ao abrir PDF: {e}")
        texto = ""

    # Se texto nativo vazio, usar OCR
    if not texto.strip() and texto_ocr.strip():
        texto = texto_ocr
        resultado.avisos.append("Texto extraído via OCR (documento escaneado)")

    if not texto.strip():
        resultado.erros.append("PDF sem texto extraível (pode ser imagem — use OCR)")
        return resultado

    return _parsear_texto_carta(texto, resultado)


def parsear_carta_concessao_texto(texto: str) -> ResultadoParserCarta:
    """Versão para testes: aceita texto diretamente."""
    resultado = ResultadoParserCarta()
    return _parsear_texto_carta(texto, resultado)


def _parsear_texto_carta(texto: str, resultado: ResultadoParserCarta) -> ResultadoParserCarta:
    b = DadosBeneficio()

    # ── Dados do segurado ─────────────────────────────────────────────────────
    b.nome_segurado = _campo(texto, [
        r"(?:Nome|NOME)[:\s]+([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚa-záéíóúâêîôûãõçàü\s]{5,60})",
        r"Requerente[:\s]+([A-ZÁÉÍÓÚ][A-Za-záéíóú\s]{5,60})",
        r"[Nn]ome[:\s]+([A-Z][A-Za-zÁÉÍÓÚáéíóúâêîôûãõçàü\s]{5,60})",
    ])
    b.cpf = _campo(texto, [
        r"CPF[:\s/]*(\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\-\.]?\d{2})",
        r"[CG][PF][FP][:\s/]*(\d{3}[\.\- ]?\d{3}[\.\- ]?\d{3}[\-\. ]?\d{2})",  # OCR: CPF→GPF, etc
    ])
    if b.cpf:
        b.cpf = re.sub(r"[.\-/ ]", "", b.cpf)

    b.nit = _campo(texto, [
        r"NIT[:\s]*(\d{3}[\.\-]?\d{5}[\.\-]?\d{2}[\-\.]?\d{1})",
        r"PIS[/\-]PASEP[:\s]*(\d[\d\.\-]+)",
        r"N[l1I]T[:\s]*(\d[\d\.\- ]+)",  # OCR: NIT→N1T, NlT
    ])

    # ── Número do benefício ───────────────────────────────────────────────────
    b.numero_beneficio = _campo(texto, [
        r"(?:N[uú]mero\s*(?:do\s*)?Benef[ií]cio|NB|Benef\.?)[:\s]*(\d{10})",
        r"[Bb]enef[ií]cio[:\s]+(\d{10})",
        r"\b(\d{3}[\.\-]?\d{3}[\.\-]?\d{4}[\-\.]?\d{1})\b",
        r"[Nn]umero\s*(?:do\s*)?[Bb]enef[^\n]*?(\d{10})",  # OCR sem acento
    ])
    if b.numero_beneficio:
        b.numero_beneficio = re.sub(r"[.\-]", "", b.numero_beneficio)

    # ── Espécie ───────────────────────────────────────────────────────────────
    b.especie = _campo(texto, [
        r"[Ee]sp[eé]cie[:\s]+(\d{2,3})",
        r"Esp\.?[:\s]+(\d{2,3})",
    ])
    b.descricao_especie = _campo(texto, [
        r"[Ee]sp[eé]cie[:\s]+\d{2,3}[:\s\-–]+([A-Za-záéíóú][^\n]{10,80})",
        r"(Aposentadoria[^\n]{5,80})",
        r"(Auxílio[^\n]{5,60})",
        r"(Pensão[^\n]{5,60})",
        r"(Aposent[^\n]{5,80})",  # OCR truncado
    ])
    if b.descricao_especie:
        b.descricao_especie = b.descricao_especie.strip()

    # ── Datas ─────────────────────────────────────────────────────────────────
    dib_str = _campo(texto, [
        r"DIB[:\s]+(\d{2}/\d{2}/\d{4})",
        r"[Dd]ata\s*(?:de\s*)?[Ii]n[ií]cio\s*(?:do\s*)?[Bb]enef[ií]cio[:\s]+(\d{2}/\d{2}/\d{4})",
        r"[Ii]n[ií]cio\s*(?:do\s*)?[Bb]enef[ií]cio[:\s]+(\d{2}/\d{2}/\d{4})",
        r"D[l1I]B[:\s]+(\d{2}/\d{2}/\d{4})",  # OCR: DIB→D1B, DlB
    ])
    b.dib = _parse_data(dib_str, resultado, "DIB")

    dip_str = _campo(texto, [
        r"DIP[:\s]+(\d{2}/\d{2}/\d{4})",
        r"[Dd]ata\s*(?:de\s*)?[Ii]n[ií]cio\s*(?:do\s*)?[Pp]agamento[:\s]+(\d{2}/\d{2}/\d{4})",
        r"[Ii]n[ií]cio\s*(?:do\s*)?[Pp]agamento[:\s]+(\d{2}/\d{2}/\d{4})",
        r"D[l1I]P[:\s]+(\d{2}/\d{2}/\d{4})",  # OCR: DIP→D1P
    ])
    b.dip = _parse_data(dip_str, resultado, "DIP")

    dcb_str = _campo(texto, [
        r"DCB[:\s]+(\d{2}/\d{2}/\d{4})",
        r"[Dd]ata\s*(?:de\s*)?[Cc]essa[çc][ãa]o[:\s]+(\d{2}/\d{2}/\d{4})",
    ])
    if dcb_str:
        b.dcb = _parse_data(dcb_str, resultado, "DCB")

    # ── Valores monetários ────────────────────────────────────────────────────
    rmi_str = _campo(texto, [
        r"RMI[:\s]+R?\$?\s*([\d\.]+,\d{2})",
        r"[Rr]enda\s*[Mm]ensal\s*[Ii]nicial[:\s]+R?\$?\s*([\d\.]+,\d{2})",
        r"[Vv]alor\s*(?:do\s*)?[Bb]enef[ií]cio[:\s]+R?\$?\s*([\d\.]+,\d{2})",
        r"RM[l1I][:\s]+R?\$?\s*([\d\.]+,\d{2})",  # OCR: RMI→RM1
    ])
    b.rmi = _parse_decimal(rmi_str, resultado, "RMI")

    sb_str = _campo(texto, [
        r"[Ss]al[aá]rio\s*(?:de\s*)?[Bb]enef[ií]cio[:\s]+R?\$?\s*([\d\.]+,\d{2})",
        r"SB[:\s]+R?\$?\s*([\d\.]+,\d{2})",
    ])
    b.salario_beneficio = _parse_decimal(sb_str, resultado, "Salário de Benefício")

    fp_str = _campo(texto, [
        r"[Ff]ator\s*[Pp]revidenci[aá]rio[:\s]+([\d,]+)",
        r"FP[:\s]+([\d,]+)",
    ])
    if fp_str:
        try:
            b.fator_previdenciario = Decimal(fp_str.replace(",", "."))
        except InvalidOperation:
            pass

    coef_str = _campo(texto, [
        r"[Cc]oeficiente[:\s]+([\d,]+)\s*%",
        r"Coef\.?[:\s]+([\d,]+)\s*%",
    ])
    if coef_str:
        try:
            b.coeficiente = Decimal(coef_str.replace(",", ".")) / Decimal("100")
        except InvalidOperation:
            pass

    # ── Competência de início de pagamento ────────────────────────────────────
    b.competencia_inicio_pagamento = _campo(texto, [
        r"[Cc]ompet[eê]ncia[:\s]+(\d{2}/\d{4})",
        r"Comp\.?[:\s]+(\d{2}/\d{4})",
    ])

    # ── Busca genérica de datas (fallback para OCR) ──────────────────────────
    if not b.dib:
        # Tentar encontrar qualquer data DD/MM/YYYY no texto
        datas_encontradas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
        if datas_encontradas:
            # Primeira data é geralmente a DIB em cartas de concessão
            b.dib = _parse_data(datas_encontradas[0], resultado, "DIB (inferida)")
            resultado.avisos.append(f"DIB inferida do contexto: {datas_encontradas[0]}")

    # ── Busca genérica de valores (fallback para OCR) ─────────────────────────
    if not b.rmi:
        valores = re.findall(r'R?\$\s*([\d\.]+,\d{2})', texto)
        if valores:
            # Maior valor tende a ser o salário/RMI
            parsed_vals = []
            for v in valores:
                try:
                    parsed_vals.append((Decimal(v.replace(".", "").replace(",", ".")), v))
                except InvalidOperation:
                    pass
            if parsed_vals:
                parsed_vals.sort(reverse=True)
                b.rmi = parsed_vals[0][0]
                resultado.avisos.append(f"RMI inferida do contexto: R$ {parsed_vals[0][1]}")

    # ── Validação mínima ──────────────────────────────────────────────────────
    # Aceitar se encontrou pelo menos DIB ou RMI (antes exigia ambos)
    if not b.dib and not b.rmi:
        resultado.erros.append(
            "Não foi possível identificar DIB nem RMI na Carta de Concessão."
        )
        return resultado

    if not b.dib:
        resultado.avisos.append("DIB não encontrada — verifique o documento.")
    if not b.rmi:
        resultado.avisos.append("RMI não encontrada — verifique o documento.")

    resultado.beneficio = b
    resultado.sucesso = True
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _campo(texto: str, padroes: list) -> Optional[str]:
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_data(s: Optional[str], res: ResultadoParserCarta, nome: str) -> Optional[date]:
    if not s:
        return None
    try:
        p = s.split("/")
        return date(int(p[2]), int(p[1]), int(p[0]))
    except Exception:
        res.avisos.append(f"{nome} inválida: {s}")
        return None


def _parse_decimal(s: Optional[str], res: ResultadoParserCarta, nome: str) -> Optional[Decimal]:
    if not s:
        return None
    try:
        return Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation:
        res.avisos.append(f"Valor inválido para {nome}: {s}")
        return None
