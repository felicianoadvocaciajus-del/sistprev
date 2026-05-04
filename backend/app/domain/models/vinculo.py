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
        """
        Data fim efetiva para cálculo de TC.

        REGRA: Se data_fim não está informada (vínculo sem baixa no CNIS),
        usa o ÚLTIMO MÊS DE CONTRIBUIÇÃO do próprio vínculo como data fim.
        Isso evita que vínculos sem data_fim se estendam até hoje,
        inflando artificialmente o TC.

        Só usa date.today() se NÃO há nenhuma contribuição registrada
        E não há data_fim — situação de vínculo realmente em aberto/ativo.
        """
        if self.data_fim:
            return self.data_fim
        # Sem data_fim: usar último mês de contribuição + último dia do mês
        if self.contribuicoes:
            ultima_comp = max(c.competencia for c in self.contribuicoes)
            # Último dia do mês da última contribuição
            from calendar import monthrange
            ultimo_dia = monthrange(ultima_comp.year, ultima_comp.month)[1]
            return date(ultima_comp.year, ultima_comp.month, ultimo_dia)
        # Sem data_fim e sem contribuições: vínculo realmente em aberto
        return date.today()

    @property
    def data_fim_inferida(self) -> bool:
        """
        True quando a data fim foi inferida da última contribuição
        (data_fim não estava no CNIS). Usado para sinalizar em vermelho no frontend.
        """
        return self.data_fim is None and bool(self.contribuicoes)

    @property
    def duracao_dias(self) -> int:
        """Duração em dias corridos (inclusive)."""
        return (self.data_fim_efetiva - self.data_inicio).days + 1

    @property
    def is_especial(self) -> bool:
        return self.tipo_atividade != TipoAtividade.NORMAL

    @property
    def is_em_aberto(self) -> bool:
        """
        True apenas se não tem data_fim E não tem contribuições
        (vínculo genuinamente em aberto/ativo).
        """
        return self.data_fim is None and not self.contribuicoes

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
