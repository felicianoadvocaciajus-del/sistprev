"""
Modelo central do segurado previdenciário.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List

from .vinculo import Vinculo
from .contribuicao import Contribuicao
from ..enums import Sexo, TipoBeneficio


@dataclass
class DadosPessoais:
    nome: str
    data_nascimento: date
    sexo: Sexo
    cpf: str = ""
    nit: str = ""       # NIT/PIS/PASEP
    nome_mae: str = ""
    data_obito: Optional[date] = None

    @property
    def idade_na_data(self) -> callable:
        """Retorna uma função que calcula a idade em uma data específica."""
        def calcular(data_ref: date) -> Decimal:
            anos = data_ref.year - self.data_nascimento.year
            # Verifica se já fez aniversário no ano de referência
            aniv_este_ano = date(data_ref.year, self.data_nascimento.month, self.data_nascimento.day)
            if data_ref < aniv_este_ano:
                anos -= 1
            # Fração do mês
            dias_desde_aniv = (data_ref - date(
                data_ref.year if data_ref >= aniv_este_ano else data_ref.year - 1,
                self.data_nascimento.month,
                self.data_nascimento.day
            )).days
            return Decimal(str(anos)) + Decimal(str(dias_desde_aniv)) / Decimal("365.25")
        return calcular


@dataclass
class BeneficioAnterior:
    """Benefício previdenciário já recebido (constante no CNIS)."""
    numero_beneficio: str
    especie: TipoBeneficio
    dib: date
    dcb: Optional[date] = None    # Data de Cessação do Benefício (None = em curso)
    rmi: Decimal = field(default=Decimal("0"))

    @property
    def ativo(self) -> bool:
        return self.dcb is None


@dataclass
class Segurado:
    """
    Entidade central que reúne todos os dados do segurado
    para processamento pelo motor de cálculo.
    """
    dados_pessoais: DadosPessoais
    vinculos: List[Vinculo] = field(default_factory=list)
    beneficios_anteriores: List[BeneficioAnterior] = field(default_factory=list)

    # Metadados do processo
    der: Optional[date] = None      # Data de Entrada do Requerimento
    dib: Optional[date] = None      # Data de Início do Benefício (para revisões)
    observacoes: str = ""

    @property
    def sexo(self) -> Sexo:
        return self.dados_pessoais.sexo

    @property
    def data_nascimento(self) -> date:
        return self.dados_pessoais.data_nascimento

    def idade_na(self, data_ref: date) -> Decimal:
        """Calcula a idade exata em uma data específica (em anos decimais)."""
        return self.dados_pessoais.idade_na_data(data_ref)

    def vinculos_rgps(self) -> List[Vinculo]:
        """Apenas vínculos no RGPS (exclui RPPS)."""
        from ..enums import RegimePrevidenciario
        return [v for v in self.vinculos if v.regime == RegimePrevidenciario.RGPS]

    def todas_contribuicoes(self) -> List[Contribuicao]:
        """Todas as contribuições de todos os vínculos, ordenadas por competência."""
        todas = []
        for v in self.vinculos:
            todas.extend(v.contribuicoes)
        return sorted(set(todas))  # set remove duplicatas de mesma competência

    def adicionar_vinculo(self, vinculo: Vinculo) -> None:
        self.vinculos.append(vinculo)
        self.vinculos.sort(key=lambda v: v.data_inicio)
