from __future__ import annotations

from ...extensions import db
from ...models import Contrato, Fornecedor, JulgamentoCnae
from .base import Contexto, Regra, Resultado

# Associações (3xxx) e cooperativas (2143): o CNAE não descreve o que fornecem — e a Lei 11.947/2009
# permite que forneçam à merenda escolar (PNAE). Não são julgadas.
NATUREZAS_IGNORADAS = ("3", "2143")


def atividades(f: Fornecedor) -> str:
    texto = f"Principal: {f.cnae_descricao}"
    if f.cnaes_secundarios:
        texto += f"\nSecundárias: {f.cnaes_secundarios}"
    return texto


class CnaeIncompativel(Regra):
    codigo = "cnae"
    nome = "Atividade da empresa incompatível com o objeto"
    base_legal = "Lei 14.133/2021, art. 67 (qualificação técnica)"
    descricao = ("O modelo de linguagem compara o objeto do contrato com as atividades (CNAE principal e "
                 "secundárias) da empresa. Associações e cooperativas não são avaliadas. Por ser um julgamento "
                 "automatizado, esta regra tem peso menor.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        f = contrato.fornecedor
        if f is None or f.tipo != "PJ" or not f.cnae_descricao or not contrato.objeto:
            return None
        if f.natureza_juridica and f.natureza_juridica.startswith(NATUREZAS_IGNORADAS):
            return None
        cnae = atividades(f)
        j = JulgamentoCnae.query.filter_by(contrato_id=contrato.id).first() if contrato.id else None
        valido = j is not None and j.cnae_descricao == cnae and j.objeto == contrato.objeto
        modelo = getattr(ctx.llm, "model", None)
        if ctx.llm is not None and (not valido or j.modelo != modelo):
            resposta = ctx.llm.cnae_compativel(contrato.objeto, cnae)
            if resposta is not None:
                j = j or JulgamentoCnae(contrato_id=contrato.id)
                j.cnae_descricao, j.objeto, j.modelo = cnae, contrato.objeto, modelo
                j.compativel, j.justificativa = resposta
                db.session.add(j)
                valido = True
            # LLM falhou: nada é guardado; vale o julgamento anterior, se ainda for para estes dados
        if not valido:
            return None  # sem julgamento para o CNAE e o objeto atuais
        if j.compativel:
            return None
        return self.resultado(contrato, {"objeto": contrato.objeto, "cnae": f.cnae_descricao,
                                         "cnaes_secundarios": f.cnaes_secundarios,
                                         "justificativa": j.justificativa, "modelo": j.modelo})
