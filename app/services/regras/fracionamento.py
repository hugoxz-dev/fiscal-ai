from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS
from .dispensa import dispensa_por_valor, limite_dispensa
from .qualidade import sem_duplicatas
from .sobrepreco import STOP_WORDS


def _similaridades(ctx: Contexto) -> dict[int, dict[int, float]]:
    """Similaridade TF-IDF entre os objetos das dispensas por valor (calculada uma vez por contexto)."""
    if "fracionamento_sim" not in ctx.extras:
        dispensas = [c for c in ctx.contratos if dispensa_por_valor(c) and c.objeto]
        tabela: dict[int, dict[int, float]] = {}
        if len(dispensas) >= 2:
            matriz = TfidfVectorizer(strip_accents="unicode", lowercase=True,
                                     stop_words=STOP_WORDS).fit_transform([c.objeto for c in dispensas])
            sim = cosine_similarity(matriz)
            tabela = {a.id: {b.id: float(sim[i, j]) for j, b in enumerate(dispensas)} for i, a in enumerate(dispensas)}
        ctx.extras["fracionamento_sim"] = tabela
    return ctx.extras["fracionamento_sim"]


class Fracionamento(Regra):
    codigo = "fracionamento"
    nome = "Possível fracionamento de despesa"
    base_legal = "Lei 14.133/2021, art. 75, §1º"
    descricao = ("Várias dispensas do mesmo órgão para o mesmo fornecedor no mesmo ano, com objetos da mesma "
                 f"natureza (similaridade TF-IDF ≥ {PARAMS['fracionamento_similaridade']:g}), cada uma abaixo do "
                 "limite, mas que somadas o ultrapassam.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not dispensa_por_valor(contrato) or not contrato.data_assinatura:
            return None
        limite, _ = limite_dispensa(contrato)
        if contrato.valor_global is None or contrato.valor_global > limite:
            return None
        semelhantes = _similaridades(ctx).get(contrato.id, {})
        limiar = PARAMS["fracionamento_similaridade"]
        grupo = [c for c in ctx.contratos
                 if dispensa_por_valor(c) and c.orgao_id == contrato.orgao_id
                 and c.fornecedor_id == contrato.fornecedor_id and c.data_assinatura
                 and c.data_assinatura.year == contrato.data_assinatura.year
                 and c.valor_global is not None and c.valor_global <= limite
                 and (c.id == contrato.id or semelhantes.get(c.id, 0.0) >= limiar)]
        grupo = sem_duplicatas(grupo, contrato)
        if len(grupo) < 2:
            return None
        soma = sum(c.valor_global for c in grupo)
        if soma <= limite:
            return None
        return self.resultado(contrato, {"soma": fmt(soma), "limite": fmt(limite),
                                         "ano": contrato.data_assinatura.year,
                                         "contratos": [c.id for c in grupo],
                                         "valores": [fmt(c.valor_global) for c in grupo]})
