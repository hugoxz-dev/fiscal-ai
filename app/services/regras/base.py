"""Estrutura comum das regras de risco."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from ...models import Contrato, Sancao


@dataclass
class Resultado:
    codigo: str
    pontos: int
    evidencia: dict


@dataclass
class Contexto:
    contratos: list[Contrato]               # todos os contratos do período (para regras comparativas)
    sancoes: dict[str, list[Sancao]]        # sanções por documento do fornecedor
    llm: object | None = None               # OllamaClient ou None
    extras: dict = field(default_factory=dict)  # cache para regras com preparação


def fmt(v) -> str:
    """Decimal -> string com 2 casas (JSON-serializável e estável)."""
    return str(Decimal(v).quantize(Decimal("0.01")))


class Regra(ABC):
    codigo: str = ""
    nome: str = ""
    base_legal: str = ""
    descricao: str = ""

    def __init__(self, pesos: dict):
        self.pesos = pesos

    @property
    def peso(self) -> int:
        return self.pesos[self.codigo]

    def resultado(self, contrato: Contrato, evidencia: dict) -> Resultado:
        evidencia = {**evidencia, "link": contrato.link_pncp}
        return Resultado(self.codigo, self.peso, evidencia)

    @abstractmethod
    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None: ...
