from __future__ import annotations

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .dispensa import dispensa_por_valor, limite_dispensa


class Fracionamento(Regra):
    codigo = "fracionamento"
    nome = "Possível fracionamento de despesa"
    base_legal = "Lei 14.133/2021, art. 75, §1º"
    descricao = ("Várias dispensas do mesmo órgão para o mesmo fornecedor no mesmo ano, cada uma abaixo do "
                 "limite, mas que somadas o ultrapassam.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not dispensa_por_valor(contrato) or not contrato.data_assinatura:
            return None
        limite, _ = limite_dispensa(contrato)
        if contrato.valor_global is None or contrato.valor_global > limite:
            return None
        grupo = [c for c in ctx.contratos
                 if dispensa_por_valor(c) and c.orgao_id == contrato.orgao_id
                 and c.fornecedor_id == contrato.fornecedor_id and c.data_assinatura
                 and c.data_assinatura.year == contrato.data_assinatura.year
                 and c.valor_global is not None and c.valor_global <= limite]
        if len(grupo) < 2:
            return None
        soma = sum(c.valor_global for c in grupo)
        if soma <= limite:
            return None
        return self.resultado(contrato, {"soma": fmt(soma), "limite": fmt(limite),
                                         "ano": contrato.data_assinatura.year,
                                         "contratos": [c.id for c in grupo],
                                         "valores": [fmt(c.valor_global) for c in grupo]})
