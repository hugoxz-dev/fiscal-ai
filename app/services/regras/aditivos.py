from __future__ import annotations

from decimal import Decimal

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS


class AditivosExcessivos(Regra):
    codigo = "aditivos"
    nome = "Aditivos acima do limite legal"
    base_legal = "Lei 14.133/2021, art. 125"
    descricao = (f"A soma dos acréscimos por termos aditivos passa de {int(PARAMS['aditivo_max_pct'] * 100)}% "
                 "do valor inicial do contrato.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not contrato.aditivos or not contrato.valor_inicial:
            return None
        soma = sum((a.valor_acrescimo or Decimal(0)) for a in contrato.aditivos)
        pct = float(soma / contrato.valor_inicial)
        if pct <= PARAMS["aditivo_max_pct"]:
            return None
        return self.resultado(contrato, {
            "percentual": round(pct * 100, 1), "valor_inicial": fmt(contrato.valor_inicial),
            "soma_acrescimos": fmt(soma),
            "aditivos": [{"numero": a.numero, "valor": fmt(a.valor_acrescimo or 0), "origem": a.origem,
                          "data": a.data.isoformat() if a.data else None} for a in contrato.aditivos],
        })
