"""
Modelos para períodos de tempo de contribuição calculados.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from ..enums import TipoAtividade


@dataclass
class Periodo:
    """
    Período contínuo de trabalho ou contribuição.
    Usado internamente pelo motor de tempo.
    """
    data_inicio: date
    data_fim: date
    tipo_atividade: TipoAtividade = TipoAtividade.NORMAL
    observacao: Optional[str] = None

    @property
    def dias(self) -> int:
        return (self.data_fim - self.data_inicio).days + 1

    def sobrepoe(self, outro: "Periodo") -> bool:
        """Verifica se este período se sobrepõe com outro."""
        return self.data_inicio <= outro.data_fim and self.data_fim >= outro.data_inicio

    def __lt__(self, other: "Periodo") -> bool:
        return self.data_inicio < other.data_inicio


@dataclass
class PeriodoEspecial(Periodo):
    """
    Período de atividade especial (insalubre/perigosa).
    Carrega o fator de conversão aplicável.
    """
    fator_conversao: Decimal = field(default=Decimal("1.0"))
    dias_convertidos: int = 0   # dias após aplicação do fator

    def __post_init__(self):
        if not isinstance(self.fator_conversao, Decimal):
            self.fator_conversao = Decimal(str(self.fator_conversao))

    def converter(self) -> int:
        """Retorna os dias convertidos para tempo comum."""
        return int((Decimal(str(self.dias)) * self.fator_conversao).to_integral_value())


@dataclass
class TempoContribuicao:
    """
    Resultado consolidado da contagem de tempo de contribuição.
    """
    dias_total: int = 0           # Total em dias (tempo comum + convertido)
    dias_comum: int = 0           # Apenas tempo comum
    dias_especial_convertido: int = 0  # Tempo especial já convertido

    @property
    def anos(self) -> int:
        return self.dias_total // 365

    @property
    def meses_restantes(self) -> int:
        return (self.dias_total % 365) // 30

    @property
    def dias_restantes(self) -> int:
        return (self.dias_total % 365) % 30

    @property
    def anos_decimal(self) -> Decimal:
        """Tempo de contribuição em anos decimais (para fator previdenciário)."""
        return Decimal(str(self.dias_total)) / Decimal("365.25")

    def formatar(self) -> str:
        return f"{self.anos} anos, {self.meses_restantes} meses e {self.dias_restantes} dias"

    def __add__(self, other: "TempoContribuicao") -> "TempoContribuicao":
        return TempoContribuicao(
            dias_total=self.dias_total + other.dias_total,
            dias_comum=self.dias_comum + other.dias_comum,
            dias_especial_convertido=self.dias_especial_convertido + other.dias_especial_convertido,
        )
