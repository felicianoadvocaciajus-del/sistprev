"""
Modelos de contribuição previdenciária.

REGRA CRÍTICA: Todos os valores monetários são Decimal.
               Competências são date com dia sempre = 1.
               NUNCA usar float ou string para valores financeiros.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


def competencia(ano: int, mes: int) -> date:
    """Cria uma competência (sempre dia 01 do mês)."""
    return date(ano, mes, 1)


def competencia_str(s: str) -> date:
    """
    Converte string de competência para date.
    Aceita formatos: 'MM/AAAA', 'AAAA-MM', 'AAAA-MM-DD'.
    """
    s = s.strip()
    if len(s) == 7 and s[2] == "/":
        mes, ano = int(s[:2]), int(s[3:])
        return date(ano, mes, 1)
    elif len(s) == 7 and s[4] == "-":
        ano, mes = int(s[:4]), int(s[5:])
        return date(ano, mes, 1)
    elif len(s) == 10 and s[4] == "-":
        return date(int(s[:4]), int(s[5:7]), 1)
    raise ValueError(f"Formato de competência não reconhecido: '{s}'")


class Competencia:
    """Utilitários para operações com competências (date dia=1)."""

    @staticmethod
    def de_string(s: str) -> date:
        return competencia_str(s)

    @staticmethod
    def criar(ano: int, mes: int) -> date:
        return date(ano, mes, 1)

    @staticmethod
    def proxima(c: date) -> date:
        if c.month == 12:
            return date(c.year + 1, 1, 1)
        return date(c.year, c.month + 1, 1)

    @staticmethod
    def anterior(c: date) -> date:
        if c.month == 1:
            return date(c.year - 1, 12, 1)
        return date(c.year, c.month - 1, 1)

    @staticmethod
    def intervalo(inicio: date, fim: date) -> list[date]:
        """Retorna todas as competências entre inicio e fim, inclusive."""
        competencias = []
        atual = date(inicio.year, inicio.month, 1)
        fim_norm = date(fim.year, fim.month, 1)
        while atual <= fim_norm:
            competencias.append(atual)
            atual = Competencia.proxima(atual)
        return competencias

    @staticmethod
    def diferenca_meses(c1: date, c2: date) -> int:
        """Número de meses de diferença entre duas competências (c2 - c1)."""
        return (c2.year - c1.year) * 12 + (c2.month - c1.month)

    @staticmethod
    def formatar(c: date) -> str:
        return c.strftime("%m/%Y")


@dataclass
class Contribuicao:
    """
    Representa uma competência de contribuição previdenciária.

    competencia: date com dia=1 (mês de referência)
    salario_contribuicao: valor bruto informado (pode estar acima do teto)
    teto_aplicado: teto vigente nessa competência
    salario_corrigido: valor após correção monetária até a DER (preenchido pelo motor)
    indice_correcao: fator de correção aplicado (preenchido pelo motor)
    valida_carencia: se essa competência conta para carência
    valida_tc: se essa competência conta para tempo de contribuição
    """
    competencia: date
    salario_contribuicao: Decimal

    # Preenchidos após processamento
    teto_aplicado: Decimal = field(default=Decimal("0"))
    salario_corrigido: Decimal = field(default=Decimal("0"))
    indice_correcao: Decimal = field(default=Decimal("1"))
    valida_carencia: bool = True
    valida_tc: bool = True
    observacao: Optional[str] = None  # ex: "MATERNIDADE", "INVALIDEZ", "ABAIXO_MINIMO"

    def __post_init__(self):
        # Garantir que competência sempre seja dia 1
        self.competencia = date(self.competencia.year, self.competencia.month, 1)
        # Garantir Decimal
        if not isinstance(self.salario_contribuicao, Decimal):
            self.salario_contribuicao = Decimal(str(self.salario_contribuicao))
        if not isinstance(self.teto_aplicado, Decimal):
            self.teto_aplicado = Decimal(str(self.teto_aplicado))

    @property
    def salario_limitado_teto(self) -> Decimal:
        """Salário limitado ao teto do RGPS (valor nominal, sem correção)."""
        if self.teto_aplicado > 0:
            return min(self.salario_contribuicao, self.teto_aplicado)
        return self.salario_contribuicao

    def __lt__(self, other: "Contribuicao") -> bool:
        return self.competencia < other.competencia

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contribuicao):
            return False
        return self.competencia == other.competencia

    def __hash__(self):
        return hash(self.competencia)
