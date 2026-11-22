"""Filtros de qualidade dos dados usados pelas regras comparativas (validação manual de 2026-11-22)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal

from ...models import Contrato
from .base import Contexto
from .config import PARAMS


def objeto_normalizado(c: Contrato) -> str:
    return " ".join(re.findall(r"\w+", (c.objeto or "").lower()))


def chave_duplicata(c: Contrato) -> tuple:
    """O mesmo contrato publicado duas vezes no PNCP: mesmo fornecedor, valor, data e objeto (sem pontuação)."""
    return (c.fornecedor_id, c.valor_global, c.data_assinatura, objeto_normalizado(c))


def sem_duplicatas(contratos: list[Contrato], primeiro: Contrato | None = None) -> list[Contrato]:
    """Mantém um contrato por chave de duplicata; `primeiro`, se dado, é o representante do seu grupo."""
    ordem = ([primeiro] if primeiro is not None else []) + [c for c in contratos if c is not primeiro]
    vistos, unicos = set(), []
    for c in ordem:
        if chave_duplicata(c) not in vistos:
            vistos.add(chave_duplicata(c))
            unicos.append(c)
    return unicos


def _casas_deslocadas(maior: Decimal, menor: Decimal) -> bool:
    """`maior` é `menor` com as casas decimais deslocadas (x100, x1000...), a partir de `valor_erro_fator`."""
    fator = Decimal(PARAMS["valor_erro_fator"])
    while fator <= maior / menor:
        if maior == menor * fator:
            return True
        fator *= 10
    return False


def valores_suspeitos(ctx: Contexto) -> set[int]:
    """Contratos com valor provavelmente digitado errado: o mesmo fornecedor tem o mesmo objeto por um valor
    igual com as casas decimais deslocadas (ex.: a locação de R$ 1,5 milhão publicada como R$ 1,5 bilhão).
    Razão grande que não é potência de 10 não conta: em ata de registro de preços é só quantidade diferente."""
    if "valores_suspeitos" not in ctx.extras:
        grupos = defaultdict(list)
        for c in ctx.contratos:
            if c.valor_global and c.valor_global > 0 and c.objeto:
                grupos[(c.fornecedor_id, objeto_normalizado(c))].append(c)
        ctx.extras["valores_suspeitos"] = {c.id for grupo in grupos.values() for c in grupo
                                           if any(_casas_deslocadas(c.valor_global, x.valor_global) for x in grupo)}
    return ctx.extras["valores_suspeitos"]


def anos_cobertos(ctx: Contexto) -> set[int]:
    """Anos com coleta completa: pelo menos `ano_cobertura_min` dos contratos do ano mais coletado. Contratos
    assinados em outros anos só entram no banco quando publicados (ou aditados) no período coletado."""
    if "anos_cobertos" not in ctx.extras:
        por_ano = Counter(c.data_assinatura.year for c in ctx.contratos if c.data_assinatura)
        maior = max(por_ano.values(), default=0)
        ctx.extras["anos_cobertos"] = {a for a, n in por_ano.items() if n >= PARAMS["ano_cobertura_min"] * maior}
    return ctx.extras["anos_cobertos"]
