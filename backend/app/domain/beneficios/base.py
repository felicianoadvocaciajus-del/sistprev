"""
Interface base para todos os calculadores de benefício.
Cada benefício implementa esta ABC.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Optional

from ..models.segurado import Segurado
from ..models.resultado import ResultadoCalculo, ResultadoRegra, ResultadoRequisitos, MemoriaCalculo
from ..enums import TipoBeneficio
from ..indices import teto_na_data
from ..indices.salario_minimo import salario_minimo_na_data


class CalculadoraBeneficio(ABC):
    """Base para todos os calculadores de benefício."""

    @property
    @abstractmethod
    def tipo_beneficio(self) -> TipoBeneficio:
        ...

    @property
    @abstractmethod
    def nome(self) -> str:
        ...

    @property
    @abstractmethod
    def base_legal(self) -> str:
        ...

    @abstractmethod
    def verificar_requisitos(
        self, segurado: Segurado, der: date
    ) -> ResultadoRequisitos:
        """Verifica se o segurado preenche os requisitos na DER."""
        ...

    @abstractmethod
    def calcular_rmi(
        self, segurado: Segurado, der: date
    ) -> ResultadoRegra:
        """Calcula a RMI e retorna o resultado com memória de cálculo."""
        ...

    def calcular(self, segurado: Segurado, der: date) -> ResultadoCalculo:
        """Método orquestrador: verifica requisitos + calcula RMI."""
        mem = MemoriaCalculo()
        mem.secao(f"BENEFÍCIO: {self.nome}")

        requisitos = self.verificar_requisitos(segurado, der)
        resultado_regra = self.calcular_rmi(segurado, der)

        rc = ResultadoCalculo(
            tipo_beneficio=self.tipo_beneficio,
            der=der,
            elegivel=requisitos.elegivel,
            resultado_principal=resultado_regra if requisitos.elegivel else None,
            cenarios=[resultado_regra],
            requisitos=requisitos,
        )
        return rc

    # ── Helpers comuns ────────────────────────────────────────────────────────

    def _teto(self, der: date) -> Decimal:
        return teto_na_data(der)

    def _piso(self, der: date) -> Decimal:
        return salario_minimo_na_data(der)

    def _aplicar_limites(self, rmi: Decimal, der: date) -> Decimal:
        """Aplica piso (salário mínimo) e teto ao valor da RMI."""
        piso = self._piso(der)
        teto = self._teto(der)
        return max(piso, min(rmi, teto))
