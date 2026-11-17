from __future__ import annotations

from ...extensions import db
from ...models import Contrato, JulgamentoCnae
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
        modelo = getattr(ctx.llm, "model", None)
        j = JulgamentoCnae.query.filter_by(contrato_id=contrato.id).first() if contrato.id else None
        if j is None or j.cnae_descricao != f.cnae_descricao or j.modelo != modelo:
            resposta = ctx.llm.cnae_compativel(contrato.objeto, f.cnae_descricao)
            if resposta is None:
                return None  # LLM falhou: não guarda, tenta de novo na próxima análise
            j = j or JulgamentoCnae(contrato_id=contrato.id)
            j.cnae_descricao, j.modelo, j.compativel, j.justificativa = f.cnae_descricao, modelo, *resposta
            db.session.add(j)
        if j.compativel:
            return None
        return self.resultado(contrato, {"objeto": contrato.objeto, "cnae": f.cnae_descricao,
                                         "justificativa": j.justificativa, "modelo": modelo})
