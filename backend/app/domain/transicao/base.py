"""Interface base para as regras de transição da EC 103/2019."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date
from ..models.segurado import Segurado
from ..models.resultado import ResultadoRegra


class RegraTransicao(ABC):
    @property
    @abstractmethod
    def nome(self) -> str: ...

    @property
    def base_legal(self) -> str:
        return "EC 103/2019"

    @abstractmethod
    def verificar_elegibilidade(self, segurado: Segurado, der: date) -> bool: ...

    @abstractmethod
    def calcular(self, segurado: Segurado, der: date) -> ResultadoRegra: ...
