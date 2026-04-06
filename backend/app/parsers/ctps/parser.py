"""
Parser da Carteira de Trabalho Digital (CTPS Digital) em PDF.

A CTPS Digital emitida pelo MTE/CAGED contém:
  - Dados pessoais do trabalhador
  - Histórico de vínculos empregatícios (admissão, demissão, CBO, remuneração)
  - Anotações gerais

O documento segue o layout do sistema e-Social / SPPE (Secretaria de Políticas
Públicas de Emprego). As informações são alimentadas diretamente pelo eSocial.

Diferença em relação ao CNIS:
  - CTPS foca em vínculos formais (CLT, domésticos)
  - Não contém contribuições mensais individuais (somente remuneração de admissão/desligamento)
  - Complementa o CNIS com datas precisas e CBO

Para dados de contribuição mensais, o CNIS deve ser usado em conjunto.
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class VinculoCTPS:
    empregador_cnpj: Optional[str] = None
    empregador_nome: Optional[str] = None
    data_admissao: Optional[date] = None
    data_demissao: Optional[date] = None
    cargo: Optional[str] = None              # CBO / cargo
    cbo: Optional[str] = None               # Código Brasileiro de Ocupação
    remuneracao_admissao: Optional[Decimal] = None
    motivo_desligamento: Optional[str] = None
    regime_jornada: Optional[str] = None    # "CLT", "DOMÉSTICO", etc.


@dataclass
class ResultadoParserCTPS:
    nome: Optional[str] = None
    cpf: Optional[str] = None
    data_nascimento: Optional[date] = None
    pis_pasep: Optional[str] = None
    vinculos: List[VinculoCTPS] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    sucesso: bool = False


def parsear_ctps_digital(caminho_pdf: str, texto_ocr: str = "") -> ResultadoParserCTPS:
    """
    Lê a CTPS Digital em PDF e extrai os vínculos de trabalho.

    Args:
        caminho_pdf: Caminho do arquivo PDF
        texto_ocr: Texto já extraído via OCR (fallback para PDFs escaneados)
    """
    resultado = ResultadoParserCTPS()

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
        resultado.erros.append("PDF sem texto extraível.")
        return resultado

    return _parsear_texto_ctps(texto, resultado)


def parsear_ctps_texto(texto: str) -> ResultadoParserCTPS:
    """Versão para testes."""
    resultado = ResultadoParserCTPS()
    return _parsear_texto_ctps(texto, resultado)


def _parsear_texto_ctps(texto: str, resultado: ResultadoParserCTPS) -> ResultadoParserCTPS:
    # ── Dados pessoais ────────────────────────────────────────────────────────
    resultado.nome = _campo(texto, [
        r"(?:Nome Completo|Nome|NOME)[:\s]+([A-ZÁÉÍÓÚ][A-Za-záéíóúâêîôûãõçàü\s]{5,60})",
        r"Trabalhador[:\s]+([A-ZÁÉÍÓÚ][A-Za-záéíóú\s]{5,60})",
    ])
    cpf = _campo(texto, [
        r"CPF[:\s/]*(\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\-\.]?\d{2})",
    ])
    resultado.cpf = re.sub(r"[.\-/]", "", cpf) if cpf else None

    dn_str = _campo(texto, [
        r"Data de Nascimento[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Nascimento[:\s]+(\d{2}/\d{2}/\d{4})",
    ])
    resultado.data_nascimento = _parse_data(dn_str, resultado, "Data de Nascimento")

    pis = _campo(texto, [
        r"PIS[/\-]PASEP[:\s]*(\d[\d\.\-]+)",
        r"NIS[:\s]*(\d{11})",
    ])
    resultado.pis_pasep = re.sub(r"[.\-]", "", pis) if pis else None

    # ── Vínculos ──────────────────────────────────────────────────────────────
    resultado.vinculos = _extrair_vinculos_ctps(texto, resultado)

    if not resultado.nome and not resultado.vinculos:
        resultado.erros.append(
            "Não foi possível identificar dados na CTPS Digital. "
            "Verifique se o documento é uma CTPS Digital válida."
        )
        return resultado

    if not resultado.nome:
        resultado.avisos.append("Nome do trabalhador não identificado.")

    resultado.sucesso = True
    return resultado


def _extrair_vinculos_ctps(texto: str, resultado: ResultadoParserCTPS) -> List[VinculoCTPS]:
    """
    Extrai blocos de vínculo da CTPS Digital.

    A CTPS Digital organiza os vínculos por:
    - Cabeçalho: CNPJ / Razão Social
    - Admissão: data, cargo, CBO, remuneração
    - Demissão (quando houver): data, motivo
    """
    vinculos = []

    # Tentativa 1: dividir por CNPJ (cada empregador tem um CNPJ no cabeçalho)
    blocos = _dividir_por_cnpj(texto)

    if not blocos:
        # Tentativa 2: dividir por "Admissão:" ou "Data de Admissão"
        partes = re.split(r"(?m)(?=Admiss[aã]o[:\s])", texto)
        blocos = [p.strip() for p in partes if len(p.strip()) > 30]

    if not blocos:
        resultado.avisos.append(
            "Não foi possível identificar vínculos na CTPS Digital. "
            "Insira os dados manualmente ou use o CNIS."
        )
        return []

    for bloco in blocos:
        v = _parsear_bloco_ctps(bloco, resultado)
        if v:
            vinculos.append(v)

    return vinculos


def _dividir_por_cnpj(texto: str) -> List[str]:
    """Divide o texto em blocos, um por CNPJ encontrado."""
    padrao = r"(?m)(?=\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})"
    partes = re.split(padrao, texto)
    return [p.strip() for p in partes if len(p.strip()) > 40]


def _parsear_bloco_ctps(bloco: str, resultado: ResultadoParserCTPS) -> Optional[VinculoCTPS]:
    v = VinculoCTPS()

    # CNPJ
    cnpj = _campo(bloco, [
        r"(\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[/\-]?\d{4}[\-\.]?\d{2})",
    ])
    v.empregador_cnpj = re.sub(r"[.\-/]", "", cnpj) if cnpj else None

    # Nome do empregador
    v.empregador_nome = _campo(bloco, [
        r"(?:Empresa|Empregador|Razão Social)[:\s]+([A-Za-záéíóúâêîôûãõçàü][^\n]{5,60})",
    ])

    # Datas
    adm_str = _campo(bloco, [
        r"(?:Data de Admiss[aã]o|Admiss[aã]o)[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Admitido em[:\s]+(\d{2}/\d{2}/\d{4})",
    ])
    v.data_admissao = _parse_data(adm_str, resultado, "Admissão")

    dem_str = _campo(bloco, [
        r"(?:Data de Demiss[aã]o|Data de Saída|Desligamento)[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Demitido em[:\s]+(\d{2}/\d{2}/\d{4})",
    ])
    v.data_demissao = _parse_data(dem_str, resultado, "Demissão")

    # Se não achou datas explícitas, tenta extrair todas as datas e assumir ordem
    if not v.data_admissao:
        datas = re.findall(r"(\d{2}/\d{2}/\d{4})", bloco)
        if datas:
            v.data_admissao = _parse_data(datas[0], resultado, "Admissão (inferida)")
        if len(datas) >= 2:
            v.data_demissao = _parse_data(datas[1], resultado, "Demissão (inferida)")

    if not v.data_admissao:
        return None  # bloco inválido sem data de admissão

    # Cargo / CBO
    v.cargo = _campo(bloco, [
        r"(?:Cargo|Função|Ocupação)[:\s]+([A-Za-záéíóú][^\n]{3,50})",
    ])
    v.cbo = _campo(bloco, [
        r"CBO[:\s]+(\d{4}[-\s]?\d{2})",
        r"C\.B\.O\.?[:\s]+(\d{4,6})",
    ])

    # Remuneração
    rem_str = _campo(bloco, [
        r"(?:Remuneração|Salário)[:\s]+R?\$?\s*([\d\.]+,\d{2})",
    ])
    if rem_str:
        try:
            v.remuneracao_admissao = Decimal(rem_str.replace(".", "").replace(",", "."))
        except InvalidOperation:
            pass

    # Motivo desligamento
    v.motivo_desligamento = _campo(bloco, [
        r"(?:Motivo|Motivo de Desligamento)[:\s]+([A-Za-záéíóú][^\n]{5,60})",
        r"(?:Rescisão|Demissão por)[:\s]+([A-Za-záéíóú][^\n]{5,60})",
    ])

    return v


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _campo(texto: str, padroes: list) -> Optional[str]:
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_data(s: Optional[str], res: ResultadoParserCTPS, nome: str) -> Optional[date]:
    if not s:
        return None
    try:
        p = s.split("/")
        return date(int(p[2]), int(p[1]), int(p[0]))
    except Exception:
        res.avisos.append(f"{nome} inválida: {s}")
        return None
