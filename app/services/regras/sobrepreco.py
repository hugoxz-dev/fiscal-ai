from __future__ import annotations

import math
from statistics import mean, median, pstdev

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS

STOP_WORDS = ["a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos",
              "para", "por", "com", "um", "uma", "ao", "aos", "que", "se", "sua", "seu", "conforme",
              "atender", "necessidades", "municipal", "municipio", "secretaria", "sao", "luis", "lote",
              "contratacao", "empresa", "aquisicao", "prestacao", "servicos", "servico"]


def _tipo(c: Contrato) -> str | None:
    return c.fornecedor.tipo if c.fornecedor else None


class Sobrepreco(Regra):
    codigo = "sobrepreco"
    nome = "Valor fora do padrão"
    base_legal = "Lei 14.133/2021, art. 23 (preço compatível com o mercado); metodologia TCU de sobrepreço"
    descricao = (f"Valor maior que {PARAMS['sobrepreco_fator']:g}× a mediana de pelo menos "
                 f"{PARAMS['sobrepreco_min_pares']} contratos com objeto semelhante (similaridade TF-IDF ≥ "
                 f"{PARAMS['sobrepreco_similaridade']:g}).")

    def __init__(self, pesos: dict):
        super().__init__(pesos)
        self._pares: dict[int, list[Contrato]] = {}

    def preparar(self, ctx: Contexto) -> None:
        contratos = [c for c in ctx.contratos if c.objeto and c.valor_global and c.valor_global > 0]
        self._pares = {}
        if len(contratos) < 2:
            return
        vetorizador = TfidfVectorizer(strip_accents="unicode", lowercase=True, stop_words=STOP_WORDS)
        matriz = vetorizador.fit_transform([c.objeto for c in contratos])
        sim = cosine_similarity(matriz)
        limiar = PARAMS["sobrepreco_similaridade"]
        for i, c in enumerate(contratos):
            # PJ só com PJ e PF só com PF: cota de agricultor (PF) não é parâmetro para associação (PJ)
            self._pares[c.id] = [contratos[j] for j in range(len(contratos)) if j != i and sim[i, j] >= limiar
                                 and _tipo(contratos[j]) == _tipo(c)]

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        pares = self._pares.get(contrato.id, [])
        if len(pares) < PARAMS["sobrepreco_min_pares"] or not contrato.valor_global:
            return None
        valores = [p.valor_global for p in pares]
        mediana = median(valores)
        fator = float(contrato.valor_global / mediana)
        if fator <= PARAMS["sobrepreco_fator"]:
            return None
        logs = [math.log(float(v)) for v in valores]
        z = (math.log(float(contrato.valor_global)) - mean(logs)) / max(pstdev(logs), 0.01)
        mais_proximos = sorted(pares, key=lambda p: abs(p.valor_global - mediana))[:5]
        return self.resultado(contrato, {
            "valor": fmt(contrato.valor_global), "mediana": fmt(mediana), "fator": round(fator, 2),
            "z_log": round(z, 2), "qtd_pares": len(pares),
            "pares": [{"id": p.id, "objeto": (p.objeto or "")[:120], "valor": fmt(p.valor_global)}
                      for p in mais_proximos],
        })
