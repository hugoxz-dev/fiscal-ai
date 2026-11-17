from __future__ import annotations

from ...models import Contrato
from .base import Contexto, Regra, Resultado


class CnaeIncompativel(Regra):
    codigo = "cnae"
    nome = "Atividade da empresa incompatível com o objeto"
    base_legal = "Lei 14.133/2021, art. 67 (qualificação técnica)"
    descricao = ("O modelo de linguagem compara o objeto do contrato com a atividade principal (CNAE) da "
                 "empresa. Por ser um julgamento automatizado, esta regra tem peso menor.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        f = contrato.fornecedor
        if ctx.llm is None or f is None or f.tipo != "PJ" or not f.cnae_descricao or not contrato.objeto:
            return None
        resposta = ctx.llm.cnae_compativel(contrato.objeto, f.cnae_descricao)
        if resposta is None or resposta[0]:
            return None
        return self.resultado(contrato, {"objeto": contrato.objeto, "cnae": f.cnae_descricao,
                                         "justificativa": resposta[1],
                                         "modelo": getattr(ctx.llm, "model", None)})
