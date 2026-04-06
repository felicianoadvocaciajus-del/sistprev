"""
OCR Engine Orchestrator — extração de texto de PDFs nativos e escaneados.

Pipeline:
1. Extrair texto nativo do PDF (pdfplumber)
2. Renderizar páginas como imagem (pdf2image + poppler)
3. Pré-processar imagem (OpenCV: deskew, denoise, binarize)
4. Rodar OCR primário (Tesseract por+eng)
5. Se confiança baixa: OCR fallback com pré-processamento diferente
6. Reconciliar texto nativo + OCR quando ambos existem
7. Registrar qualidade e proveniência por página
"""
from __future__ import annotations
import io
import os
import re
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .evidence import (
    PageQuality, ExtractionMethod, Provenance, DocumentEvidence,
)

logger = logging.getLogger("sistprev.ocr")

# Paths configuráveis
TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
POPPLER_PATH = os.environ.get(
    "POPPLER_PATH",
    r"C:\Program Files\poppler\poppler-24.08.0\Library\bin"
)

# Mínimo de caracteres para considerar que uma página tem texto nativo útil
MIN_NATIVE_CHARS = 30
# DPI para renderização de páginas
OCR_DPI = 300
# Limiar de confiança do OCR para aceitar resultado primário
OCR_CONFIDENCE_THRESHOLD = 60.0


@dataclass
class PageResult:
    """Resultado da extração de uma página."""
    page_number: int  # 1-based
    native_text: str = ""
    ocr_text: str = ""
    final_text: str = ""
    method: ExtractionMethod = ExtractionMethod.NATIVE_TEXT
    ocr_confidence: float = 0.0
    quality: float = 0.0
    issues: List[str] = field(default_factory=list)
    is_legible: bool = True


@dataclass
class DocumentResult:
    """Resultado completo da extração de um documento."""
    filename: str = ""
    total_pages: int = 0
    pages: List[PageResult] = field(default_factory=list)
    full_text: str = ""
    evidence: Optional[DocumentEvidence] = None

    @property
    def overall_quality(self) -> float:
        if not self.pages:
            return 0.0
        return sum(p.quality for p in self.pages) / len(self.pages)


def _setup_tesseract():
    """Configura pytesseract com o caminho correto."""
    try:
        import pytesseract
        if os.path.exists(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        return pytesseract
    except ImportError:
        logger.warning("pytesseract não instalado")
        return None


def _extract_native_text(pdf_path: str) -> List[Tuple[int, str]]:
    """Extrai texto nativo de cada página do PDF usando pdfplumber."""
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append((i + 1, text))
    except Exception as e:
        logger.error(f"Erro ao extrair texto nativo: {e}")
    return pages


def _render_pages_to_images(pdf_path: str, dpi: int = OCR_DPI):
    """Renderiza páginas do PDF como imagens PIL."""
    try:
        from pdf2image import convert_from_path
        poppler = POPPLER_PATH if os.path.exists(POPPLER_PATH) else None
        images = convert_from_path(
            pdf_path,
            dpi=dpi,
            poppler_path=poppler,
            fmt="png",
            thread_count=2,
        )
        return images
    except Exception as e:
        logger.error(f"Erro ao renderizar PDF: {e}")
        return []


def _preprocess_image(img, strategy: str = "standard"):
    """
    Pré-processa imagem para OCR.
    Strategies: standard, aggressive, manuscript
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        # Converter PIL -> numpy
        img_np = np.array(img)

        # Converter para escala de cinza se necessário
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np

        if strategy == "standard":
            # Denoise leve
            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            # Binarização adaptativa (boa para documentos)
            binary = cv2.adaptiveThreshold(
                denoised, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, 15
            )
            return Image.fromarray(binary)

        elif strategy == "aggressive":
            # Para documentos muito ruins: contraste forte + binarização
            # Equalização de histograma CLAHE
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            # Denoise mais forte
            denoised = cv2.fastNlMeansDenoising(enhanced, h=20)
            # Binarização Otsu
            _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # Morfologia para limpar ruído
            kernel = np.ones((1, 1), np.uint8)
            cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            return Image.fromarray(cleaned)

        elif strategy == "manuscript":
            # Para texto manuscrito: preservar mais detalhes
            denoised = cv2.fastNlMeansDenoising(gray, h=8)
            binary = cv2.adaptiveThreshold(
                denoised, 255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY, 21, 10
            )
            return Image.fromarray(binary)

        return img  # fallback: sem pré-processamento

    except ImportError:
        logger.warning("OpenCV não disponível, pulando pré-processamento")
        return img
    except Exception as e:
        logger.warning(f"Erro no pré-processamento: {e}")
        return img


def _deskew_image(img):
    """Corrige inclinação (skew) da imagem."""
    try:
        import cv2
        import numpy as np
        from PIL import Image

        img_np = np.array(img)
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np

        # Detectar ângulo de inclinação
        coords = np.column_stack(np.where(gray < 128))
        if len(coords) < 100:
            return img

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Só corrigir se inclinação significativa (> 0.5 grau)
        if abs(angle) < 0.5:
            return img

        (h, w) = img_np.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img_np, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        return Image.fromarray(rotated)

    except Exception:
        return img


def _run_ocr(img, lang: str = "por+eng", config: str = "") -> Tuple[str, float]:
    """
    Roda Tesseract OCR em uma imagem.
    Retorna (texto, confiança média).
    """
    pytesseract = _setup_tesseract()
    if pytesseract is None:
        return "", 0.0

    try:
        # Extrair texto com dados de confiança
        data = pytesseract.image_to_data(
            img, lang=lang, config=config,
            output_type=pytesseract.Output.DICT
        )

        # Calcular confiança média (ignorando blocos vazios)
        confidences = [
            int(c) for c, t in zip(data["conf"], data["text"])
            if int(c) > 0 and t.strip()
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Extrair texto completo
        text = pytesseract.image_to_string(img, lang=lang, config=config)

        return text.strip(), avg_conf

    except Exception as e:
        logger.error(f"Erro no OCR: {e}")
        return "", 0.0


def _reconcile_texts(native: str, ocr: str) -> Tuple[str, ExtractionMethod, float]:
    """
    Reconcilia texto nativo com OCR quando ambos existem.
    Retorna (texto_final, método, confiança).
    """
    native_clean = native.strip()
    ocr_clean = ocr.strip()

    if not native_clean and not ocr_clean:
        return "", ExtractionMethod.NATIVE_TEXT, 0.0

    if not native_clean:
        return ocr_clean, ExtractionMethod.OCR, 0.8

    if not ocr_clean:
        return native_clean, ExtractionMethod.NATIVE_TEXT, 0.95

    # Ambos existem — comparar densidade e conteúdo
    native_words = len(native_clean.split())
    ocr_words = len(ocr_clean.split())

    # Se o nativo tem significativamente mais texto, preferir
    if native_words > ocr_words * 1.5:
        return native_clean, ExtractionMethod.NATIVE_TEXT, 0.95

    # Se o OCR tem muito mais texto (nativo pode ser parcial)
    if ocr_words > native_words * 2:
        return ocr_clean, ExtractionMethod.OCR, 0.85

    # Caso normal: preferir nativo mas registrar como reconciliado
    return native_clean, ExtractionMethod.RECONCILED, 0.92


def extract_document(
    pdf_path: str,
    filename: str = "",
    force_ocr: bool = False,
    ocr_all_pages: bool = False,
) -> DocumentResult:
    """
    Pipeline principal de extração de texto de um PDF.

    Args:
        pdf_path: Caminho do arquivo PDF
        filename: Nome do arquivo (para registro)
        force_ocr: Forçar OCR em todas as páginas
        ocr_all_pages: Rodar OCR mesmo em páginas com texto nativo

    Returns:
        DocumentResult com texto extraído e qualidade por página
    """
    result = DocumentResult(filename=filename or os.path.basename(pdf_path))
    evidence = DocumentEvidence(document_name=result.filename)

    # 1. Extrair texto nativo
    native_pages = _extract_native_text(pdf_path)
    result.total_pages = len(native_pages)
    evidence.total_pages = result.total_pages
    evidence.log(f"Documento aberto: {result.total_pages} páginas")

    # 2. Verificar se precisa de OCR
    needs_ocr = force_ocr or ocr_all_pages
    if not needs_ocr:
        # Verificar se há páginas sem texto ou com texto insuficiente
        for page_num, text in native_pages:
            if len(text.strip()) < MIN_NATIVE_CHARS:
                needs_ocr = True
                evidence.log(f"Página {page_num}: texto nativo insuficiente ({len(text.strip())} chars)")
                break

    # 3. Se precisa de OCR, renderizar páginas
    images = []
    if needs_ocr:
        evidence.log("Renderizando páginas para OCR...")
        images = _render_pages_to_images(pdf_path)
        if not images:
            evidence.log("FALHA ao renderizar páginas — tentando só texto nativo")
            needs_ocr = False
        else:
            evidence.log(f"{len(images)} páginas renderizadas a {OCR_DPI}dpi")

    # 4. Processar cada página
    for i, (page_num, native_text) in enumerate(native_pages):
        page = PageResult(page_number=page_num)
        page.native_text = native_text
        pq = PageQuality(page_number=page_num)

        has_native = len(native_text.strip()) >= MIN_NATIVE_CHARS
        pq.has_native_text = has_native
        pq.native_text_density = len(native_text.strip()) / 3000.0  # normalizado

        do_ocr = (
            force_ocr
            or (not has_native and needs_ocr)
            or (ocr_all_pages and needs_ocr)
        )

        if do_ocr and i < len(images):
            img = images[i]

            # Deskew
            img_corrected = _deskew_image(img)

            # OCR primário com pré-processamento standard
            img_processed = _preprocess_image(img_corrected, "standard")
            ocr_text, ocr_conf = _run_ocr(img_processed)
            page.ocr_text = ocr_text
            page.ocr_confidence = ocr_conf
            pq.ocr_confidence = ocr_conf

            evidence.log(
                f"Página {page_num}: OCR standard conf={ocr_conf:.1f}% "
                f"({len(ocr_text)} chars)"
            )

            # Se confiança baixa, tentar OCR agressivo
            if ocr_conf < OCR_CONFIDENCE_THRESHOLD and ocr_conf > 0:
                evidence.log(f"Página {page_num}: confiança baixa, tentando OCR agressivo")
                img_aggressive = _preprocess_image(img_corrected, "aggressive")
                ocr_text2, ocr_conf2 = _run_ocr(img_aggressive)

                if ocr_conf2 > ocr_conf:
                    page.ocr_text = ocr_text2
                    page.ocr_confidence = ocr_conf2
                    pq.ocr_confidence = ocr_conf2
                    evidence.log(
                        f"Página {page_num}: OCR agressivo melhor conf={ocr_conf2:.1f}%"
                    )
                    page.method = ExtractionMethod.OCR_FALLBACK

            # Reconciliar
            if has_native and page.ocr_text:
                final, method, conf = _reconcile_texts(native_text, page.ocr_text)
                page.final_text = final
                page.method = method
                page.quality = conf
            elif page.ocr_text:
                page.final_text = page.ocr_text
                page.method = ExtractionMethod.OCR if page.method == ExtractionMethod.NATIVE_TEXT else page.method
                page.quality = min(page.ocr_confidence / 100.0, 0.95)
            else:
                page.final_text = native_text
                page.method = ExtractionMethod.NATIVE_TEXT
                page.quality = 0.95 if has_native else 0.0
                if not has_native:
                    page.is_legible = False
                    page.issues.append("Página ilegível — sem texto nativo e OCR falhou")
                    pq.is_legible = False
                    pq.issues.append("ILEGIVEL")
        else:
            # Sem OCR: usar texto nativo
            page.final_text = native_text
            page.method = ExtractionMethod.NATIVE_TEXT
            page.quality = 0.95 if has_native else 0.0
            if not has_native:
                page.is_legible = False
                page.issues.append("Página sem texto e sem OCR")
                pq.issues.append("SEM_TEXTO")

        pq.method_used = page.method
        pq.quality_score = page.quality
        pq.issues.extend(page.issues)

        result.pages.append(page)
        evidence.pages_quality.append(pq)

    # 5. Montar texto completo
    result.full_text = "\n\n".join(p.final_text for p in result.pages)
    result.evidence = evidence

    evidence.log(
        f"Extração concluída: qualidade média {result.overall_quality:.2f}, "
        f"{sum(1 for p in result.pages if p.is_legible)}/{result.total_pages} legíveis"
    )

    return result


def extract_document_from_bytes(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    force_ocr: bool = False,
    ocr_all_pages: bool = False,
) -> DocumentResult:
    """Extrai texto de bytes de PDF (para uploads via API)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        return extract_document(tmp_path, filename, force_ocr, ocr_all_pages)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
