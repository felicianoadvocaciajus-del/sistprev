"""
Modelos de resultado do cálculo previdenciário.
Cada cálculo retorna um ResultadoCalculo com memória completa e fundamentação legal.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List, Any

from .contribuicao import Contribuicao
from .periodo import TempoContribuicao
from ..enums import TipoBeneficio


@dataclass
class DispositivoLegal:
    """Referência a dispositivo legal aplicado no cálculo."""
    norma: str           # ex: "Lei 8.213/91"
    artigo: str          # ex: "Art. 29, §§ 5º e 6º"
    descricao: str       # ex: "Divisor mínimo do período básico de cálculo"
    url_referencia: str = ""


@dataclass
class ItemMemoria:
    """Uma linha da memória de cálculo (passo do processo)."""
    descricao: str
    valor: Optional[Any] = None
    formula: str = ""
    fundamentacao: Optional[DispositivoLegal] = None
    nivel: int = 0       # nível de indentação para relatório


@dataclass
class MemoriaCalculo:
    """
    Rastreabilidade completa de cada etapa do cálculo.
    Permite auditoria passo a passo.
    """
    itens: List[ItemMemoria] = field(default_factory=list)

    def adicionar(self, descricao: str, valor: Any = None,
                  formula: str = "", nivel: int = 0,
                  fundamentacao: Optional[DispositivoLegal] = None):
        self.itens.append(ItemMemoria(descricao, valor, formula, fundamentacao, nivel))

    def secao(self, titulo: str):
        self.itens.append(ItemMemoria(f"── {titulo} ──", nivel=0))


@dataclass
class ResultadoRequisitos:
    """Resultado da verificação de requisitos para um benefício."""
    elegivel: bool
    carencia_ok: bool
    carencia_meses_cumpridos: int
    carencia_meses_exigidos: int
    qualidade_segurado_ok: bool
    tempo_contribuicao: TempoContribuicao
    faltam_dias: int = 0         # dias para completar TC mínimo (0 = já atingiu)
    faltam_meses_carencia: int = 0
    motivos_inelegibilidade: List[str] = field(default_factory=list)


@dataclass
class ResultadoRegra:
    """
    Resultado de uma regra de transição ou regra de benefício.
    """
    nome_regra: str
    base_legal: str
    elegivel: bool
    rmi: Decimal = field(default=Decimal("0"))
    rmi_teto: Decimal = field(default=Decimal("0"))
    salario_beneficio: Decimal = field(default=Decimal("0"))
    fator_previdenciario: Optional[Decimal] = None
    coeficiente: Decimal = field(default=Decimal("0"))
    tempo_contribuicao: Optional[TempoContribuicao] = None
    data_implementacao: Optional[date] = None  # quando o segurado terá direito
    faltam_dias: int = 0
    memoria: MemoriaCalculo = field(default_factory=MemoriaCalculo)
    avisos: List[str] = field(default_factory=list)

    @property
    def rmi_formatada(self) -> str:
        return f"R$ {self.rmi_teto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class ResultadoCalculo:
    """
    Resultado completo de um cálculo previdenciário.
    Contém o resultado principal, todos os cenários alternativos
    e a memória de cálculo completa para o relatório pericial.
    """
    tipo_beneficio: TipoBeneficio
    der: date

    # Resultado principal (melhor cenário identificado)
    elegivel: bool = False
    resultado_principal: Optional[ResultadoRegra] = None

    # Todos os cenários calculados (regras de transição, revisões)
    cenarios: List[ResultadoRegra] = field(default_factory=list)

    # Requisitos verificados
    requisitos: Optional[ResultadoRequisitos] = None

    # Salários do PBC (para relatório)
    pbc: List[Contribuicao] = field(default_factory=list)
    media_salarios: Decimal = field(default=Decimal("0"))

    # Rastreabilidade
    memoria: MemoriaCalculo = field(default_factory=MemoriaCalculo)
    fundamentacao_legal: List[DispositivoLegal] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)

    def melhor_rmi(self) -> Decimal:
        """Retorna a maior RMI entre todos os cenários elegíveis."""
        elegíveis = [c for c in self.cenarios if c.elegivel and c.rmi_teto > 0]
        if not elegíveis:
            return Decimal("0")
        return max(c.rmi_teto for c in elegíveis)

    def melhor_cenario(self) -> Optional[ResultadoRegra]:
        """Retorna o cenário com maior RMI entre os elegíveis."""
        elegíveis = [c for c in self.cenarios if c.elegivel and c.rmi_teto > 0]
        if not elegíveis:
            return None
        return max(elegíveis, key=lambda c: c.rmi_teto)
