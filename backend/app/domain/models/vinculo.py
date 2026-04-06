"""
Modelo de vínculo empregatício / contributivo.
Representa um período de trabalho ou contribuição do segurado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4

from .contribuicao import Contribuicao
from ..enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado


@dataclass
class Vinculo:
    """
    Vínculo empregatício ou contributivo.

    Representa um período em que o segurado exerceu atividade
    ou recolheu contribuições ao RGPS.
    """
    id: UUID = field(default_factory=uuid4)
    tipo_vinculo: TipoVinculo = TipoVinculo.EMPREGADO
    regime: RegimePrevidenciario = RegimePrevidenciario.RGPS
    tipo_atividade: TipoAtividade = TipoAtividade.NORMAL

    # Identificação do empregador
    empregador_cnpj: Optional[str] = None
    empregador_nome: Optional[str] = None

    # Período
    data_inicio: date = field(default=date(1994, 7, 1))
    data_fim: Optional[date] = None      # None = vínculo em aberto

    # Contribuições mensais dentro deste vínculo
    contribuicoes: List[Contribuicao] = field(default_factory=list)

    # Rastreabilidade
    origem: OrigemDado = OrigemDado.MANUAL
    confianca_parser: Decimal = field(default=Decimal("1.0"))

    # Observações (indicadores do CNIS, pendências, etc.)
    indicadores: str = ""
    extemporaneo: bool = False          # Inserido fora do prazo normal
    observacao: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.confianca_parser, Decimal):
            self.confianca_parser = Decimal(str(self.confianca_parser))
        # Ordenar contribuições por competência
        self.contribuicoes.sort()

    @property
    def data_fim_efetiva(self) -> date:
        """Data fim efetiva: usa hoje se vínculo em aberto."""
        return self.data_fim or date.today()

    @property
    def duracao_dias(self) -> int:
        """Duração em dias corridos (inclusive)."""
        return (self.data_fim_efetiva - self.data_inicio).days + 1

    @property
    def is_especial(self) -> bool:
        return self.tipo_atividade != TipoAtividade.NORMAL

    @property
    def is_em_aberto(self) -> bool:
        return self.data_fim is None

    def competencias_validas(self) -> List[Contribuicao]:
        """Retorna apenas competências que contam para tempo de contribuição."""
        return [c for c in self.contribuicoes if c.valida_tc]

    def competencias_carencia(self) -> List[Contribuicao]:
        """Retorna apenas competências que contam para carência."""
        return [c for c in self.contribuicoes if c.valida_carencia]

    def __repr__(self) -> str:
        fim = self.data_fim.strftime("%m/%Y") if self.data_fim else "presente"
        return (
            f"Vinculo({self.tipo_vinculo.value}, "
            f"{self.empregador_nome or 'sem empregador'}, "
            f"{self.data_inicio.strftime('%m/%Y')}–{fim})"
        )
