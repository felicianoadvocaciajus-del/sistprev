"""
Serviço de upload e processamento de documentos.

Recebe arquivos PDF, aciona o parser adequado e retorna
um objeto Segurado pronto para cálculo.

Pipeline de extração:
1. Tenta texto nativo (pdfplumber — rápido)
2. Se falhar: executa OCR (Tesseract — mais lento, mas lê escaneados)
3. Passa texto extraído ao parser específico
"""
from __future__ import annotations
import logging
import os
import tempfile
from decimal import Decimal
from typing import Optional, Tuple, BinaryIO

from ..domain.models.segurado import Segurado, DadosPessoais
from ..domain.models.vinculo import Vinculo
from ..domain.models.contribuicao import Contribuicao
from ..domain.enums import (
    TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado, Sexo
)
from ..parsers.cnis.parser import parsear_cnis_pdf, ResultadoParserCNIS
from ..parsers.carta_concessao.parser import parsear_carta_concessao, ResultadoParserCarta
from ..parsers.ctps.parser import parsear_ctps_digital, ResultadoParserCTPS

logger = logging.getLogger("sistprev.upload")


def _extrair_texto_ocr(caminho_pdf: str, nome_arquivo: str) -> str:
    """
    Tenta extrair texto via OCR pipeline.
    Retorna string vazia se OCR não disponível ou falhar.
    """
    try:
        from ..parsers.pipeline.ocr_engine import extract_document
        logger.info(f"Iniciando OCR para: {nome_arquivo}")
        doc_result = extract_document(caminho_pdf, filename=nome_arquivo)
        if doc_result.full_text.strip():
            logger.info(
                f"OCR concluído: {doc_result.total_pages} páginas, "
                f"qualidade média {doc_result.overall_quality:.2f}"
            )
            return doc_result.full_text
        logger.warning(f"OCR não extraiu texto de: {nome_arquivo}")
    except ImportError as e:
        logger.warning(f"Dependências OCR não instaladas: {e}")
    except Exception as e:
        logger.error(f"Erro no OCR de {nome_arquivo}: {e}")
    return ""


class UploadService:

    @staticmethod
    def processar_cnis(arquivo: BinaryIO, nome_arquivo: str) -> Tuple[Optional[Segurado], ResultadoParserCNIS]:
        """
        Recebe um file-like object (PDF), salva temporariamente,
        processa com o parser e retorna (Segurado, ResultadoParser).
        Se texto nativo vazio, tenta OCR automaticamente.
        """
        caminho = _salvar_temp(arquivo, nome_arquivo)
        try:
            # Primeira tentativa: texto nativo
            resultado = parsear_cnis_pdf(caminho)

            # Se falhou por falta de texto, tentar OCR
            if not resultado.sucesso and _erro_sem_texto(resultado.erros):
                texto_ocr = _extrair_texto_ocr(caminho, nome_arquivo)
                if texto_ocr:
                    resultado = parsear_cnis_pdf(caminho, texto_ocr=texto_ocr)
        finally:
            _remover_temp(caminho)

        segurado = resultado.segurado if resultado.sucesso else None
        return segurado, resultado

    @staticmethod
    def processar_carta_concessao(arquivo: BinaryIO, nome_arquivo: str) -> Tuple[Optional[ResultadoParserCarta], str]:
        """
        Processa Carta de Concessão e retorna (ResultadoParserCarta, aviso).
        Se texto nativo vazio, tenta OCR automaticamente.
        """
        caminho = _salvar_temp(arquivo, nome_arquivo)
        try:
            resultado = parsear_carta_concessao(caminho)

            # Se falhou por falta de texto, tentar OCR
            if not resultado.sucesso and _erro_sem_texto(resultado.erros):
                texto_ocr = _extrair_texto_ocr(caminho, nome_arquivo)
                if texto_ocr:
                    resultado = parsear_carta_concessao(caminho, texto_ocr=texto_ocr)
        finally:
            _remover_temp(caminho)

        aviso = "; ".join(resultado.avisos) if resultado.avisos else ""
        return resultado if resultado.sucesso else None, aviso

    @staticmethod
    def processar_ctps(arquivo: BinaryIO, nome_arquivo: str) -> Tuple[Optional[ResultadoParserCTPS], str]:
        """Processa CTPS Digital. Tenta OCR se texto nativo vazio."""
        caminho = _salvar_temp(arquivo, nome_arquivo)
        try:
            resultado = parsear_ctps_digital(caminho)

            # Se falhou por falta de texto, tentar OCR
            if not resultado.sucesso and _erro_sem_texto(resultado.erros):
                texto_ocr = _extrair_texto_ocr(caminho, nome_arquivo)
                if texto_ocr:
                    resultado = parsear_ctps_digital(caminho, texto_ocr=texto_ocr)
        finally:
            _remover_temp(caminho)

        aviso = "; ".join(resultado.avisos) if resultado.avisos else ""
        return resultado if resultado.sucesso else None, aviso

    @staticmethod
    def mesclar_ctps_em_segurado(segurado: Segurado, ctps: ResultadoParserCTPS) -> Segurado:
        """
        Adiciona vínculos da CTPS ao segurado (sem duplicar).
        Útil quando a CTPS contém datas precisas que o CNIS não tem.

        Estratégia: se CNPJ já existe no segurado, ignora.
        Caso contrário, cria Vinculo sem contribuições mensais.
        """
        cnpjs_existentes = {
            v.empregador_cnpj for v in segurado.vinculos if v.empregador_cnpj
        }

        for vc in ctps.vinculos:
            if vc.empregador_cnpj and vc.empregador_cnpj in cnpjs_existentes:
                continue
            if not vc.data_admissao:
                continue

            # Guardar cargo/CBO da CTPS na observação para análise especial
            obs_ctps = ""
            if vc.cargo:
                obs_ctps += f"Cargo CTPS: {vc.cargo}"
            if vc.cbo:
                obs_ctps += f" | CBO: {vc.cbo}"
            v = Vinculo(
                tipo_vinculo=TipoVinculo.EMPREGADO,
                regime=RegimePrevidenciario.RGPS,
                tipo_atividade=TipoAtividade.NORMAL,
                empregador_cnpj=vc.empregador_cnpj,
                empregador_nome=vc.empregador_nome,
                data_inicio=vc.data_admissao,
                data_fim=vc.data_demissao,
                contribuicoes=[],
                origem=OrigemDado.CTPS,
                observacao=obs_ctps.strip() or None,
            )
            segurado.adicionar_vinculo(v)

        return segurado


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários internos
# ─────────────────────────────────────────────────────────────────────────────

def _erro_sem_texto(erros: list) -> bool:
    """Verifica se os erros indicam que o PDF não tem texto extraível."""
    for e in erros:
        if "sem texto" in e.lower() or "extraível" in e.lower():
            return True
    return False


def _salvar_temp(arquivo: BinaryIO, nome_original: str) -> str:
    """Salva arquivo em diretório temporário e retorna o caminho."""
    sufixo = os.path.splitext(nome_original)[1] or ".pdf"
    fd, caminho = tempfile.mkstemp(suffix=sufixo)
    try:
        with os.fdopen(fd, "wb") as f:
            conteudo = arquivo.read() if hasattr(arquivo, "read") else arquivo
            f.write(conteudo)
    except Exception:
        os.close(fd)
        raise
    return caminho


def _remover_temp(caminho: str) -> None:
    try:
        os.unlink(caminho)
    except OSError:
        pass
