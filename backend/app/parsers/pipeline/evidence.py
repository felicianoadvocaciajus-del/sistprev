"""
Motor de evidências e confiança — anti-hallucination layer.

Cada dado extraído carrega proveniência:
- documento de origem, página, trecho
- método de obtenção (NATIVE_TEXT, OCR, RECONCILED, INFERRED)
- score de confiança (0.0 a 1.0)
- status (FACT, STRONG_INDICATION, POSSIBLE, UNKNOWN)

REGRA MÁXIMA: apenas FACT (>= 0.97) entra automaticamente no cálculo.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class ExtractionMethod(str, Enum):
    NATIVE_TEXT = "NATIVE_TEXT"
    OCR = "OCR"
    OCR_FALLBACK = "OCR_FALLBACK"
    RECONCILED = "RECONCILED"
    INFERRED = "INFERRED"
    MANUAL = "MANUAL"


class EvidenceStatus(str, Enum):
    FACT = "FACT"                         # >= 0.97
    STRONG_INDICATION = "STRONG_INDICATION"  # 0.90 - 0.969
    POSSIBLE = "POSSIBLE"                 # 0.70 - 0.899
    UNKNOWN = "UNKNOWN"                   # < 0.70

    @classmethod
    def from_confidence(cls, score: float) -> "EvidenceStatus":
        if score >= 0.97:
            return cls.FACT
        elif score >= 0.90:
            return cls.STRONG_INDICATION
        elif score >= 0.70:
            return cls.POSSIBLE
        return cls.UNKNOWN


@dataclass
class Provenance:
    """Rastro de origem de um campo extraído."""
    document_type: str = ""           # CNIS, CARTA, CTPS, PPP, etc.
    document_name: str = ""           # nome do arquivo
    page_number: int = 0              # página (1-based)
    region: str = ""                  # região/trecho na página
    raw_text: str = ""                # texto bruto extraído
    method: ExtractionMethod = ExtractionMethod.NATIVE_TEXT
    confidence: float = 0.0
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    ocr_quality_score: float = 0.0    # qualidade do OCR na página (0-1)
    requires_review: bool = False
    review_reason: str = ""

    def __post_init__(self):
        self.status = EvidenceStatus.from_confidence(self.confidence)
        if self.confidence < 0.97:
            self.requires_review = True

    @property
    def is_fact(self) -> bool:
        return self.status == EvidenceStatus.FACT

    @property
    def can_auto_calculate(self) -> bool:
        """Apenas FACT entra automaticamente no cálculo."""
        return self.status == EvidenceStatus.FACT


@dataclass
class ExtractedField:
    """Campo extraído com proveniência e confiança."""
    name: str
    value: str
    provenance: Provenance = field(default_factory=Provenance)
    alternatives: List[str] = field(default_factory=list)  # valores alternativos do OCR

    @property
    def confidence(self) -> float:
        return self.provenance.confidence

    @property
    def status(self) -> EvidenceStatus:
        return self.provenance.status

    @property
    def is_fact(self) -> bool:
        return self.provenance.is_fact

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "confidence": self.provenance.confidence,
            "status": self.provenance.status.value,
            "method": self.provenance.method.value,
            "source": f"{self.provenance.document_type} p.{self.provenance.page_number}",
            "raw_text": self.provenance.raw_text,
            "requires_review": self.provenance.requires_review,
            "review_reason": self.provenance.review_reason,
            "alternatives": self.alternatives,
        }


@dataclass
class PageQuality:
    """Qualidade de leitura de uma página."""
    page_number: int
    has_native_text: bool = False
    native_text_density: float = 0.0  # chars/page area
    ocr_confidence: float = 0.0
    is_legible: bool = True
    quality_score: float = 0.0        # 0-1 score final
    issues: List[str] = field(default_factory=list)
    method_used: ExtractionMethod = ExtractionMethod.NATIVE_TEXT

    def to_dict(self) -> dict:
        return {
            "page": self.page_number,
            "quality": round(self.quality_score, 3),
            "method": self.method_used.value,
            "legible": self.is_legible,
            "issues": self.issues,
        }


@dataclass
class DocumentEvidence:
    """Registro de evidência de um documento inteiro."""
    document_name: str = ""
    document_type: str = ""           # classificação detectada
    document_type_confidence: float = 0.0
    total_pages: int = 0
    pages_quality: List[PageQuality] = field(default_factory=list)
    extracted_fields: List[ExtractedField] = field(default_factory=list)
    facts: List[ExtractedField] = field(default_factory=list)
    pending_review: List[ExtractedField] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)

    def add_field(self, f: ExtractedField):
        self.extracted_fields.append(f)
        if f.is_fact:
            self.facts.append(f)
        else:
            self.pending_review.append(f)

    def log(self, message: str):
        self.audit_trail.append(message)

    @property
    def overall_quality(self) -> float:
        if not self.pages_quality:
            return 0.0
        return sum(p.quality_score for p in self.pages_quality) / len(self.pages_quality)

    def summary(self) -> dict:
        return {
            "document_name": self.document_name,
            "document_type": self.document_type,
            "type_confidence": round(self.document_type_confidence, 3),
            "total_pages": self.total_pages,
            "overall_quality": round(self.overall_quality, 3),
            "total_fields": len(self.extracted_fields),
            "facts_count": len(self.facts),
            "pending_review_count": len(self.pending_review),
            "pages": [p.to_dict() for p in self.pages_quality],
        }
