from __future__ import annotations

import re
from decimal import Decimal

from ...models import Aditivo, Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS

_PALAVRA = re.compile(r"acr[eé]scim|supress|reajust|repactua", re.IGNORECASE)
_PERCENTUAL = re.compile(r"(\d{1,3}(?:,\d+)?)\s*%")


def _declarado_no_trecho(texto: str) -> Decimal | None:
    # Conjunto: o termo costuma repetir o mesmo percentual (no objeto e na cláusula de valor).
    acrescimos = set()
    for m in _PERCENTUAL.finditer(texto):
        palavras = list(_PALAVRA.finditer(texto, 0, m.start()))
        if palavras and palavras[-1].group(0).lower().startswith("acr"):
            acrescimos.add(Decimal(m.group(1).replace(",", ".")))
    return sum(acrescimos, Decimal(0)) if acrescimos else None


def percentual_acrescimo_declarado(texto: str | None) -> Decimal | None:
    """Percentual de acréscimo declarado no texto do termo ("acréscimo ... (22,44%) e supressão (1,35%)").
    Cada percentual pertence à última palavra-chave antes dele: só os de acréscimo contam; supressão e reajuste
    ficam de fora. O objeto e a observação do termo costumam repetir o texto, então vale o maior dos dois."""
    if not texto:
        return None
    valores = [v for trecho in texto.split("\n\n") if (v := _declarado_no_trecho(trecho)) is not None]
    return max(valores) if valores else None


def acrescimos_efetivos(contrato: Contrato) -> list[tuple[Aditivo, Decimal, str]]:
    """Acréscimo de cada termo, em ordem de data, e o critério usado. Se o termo declara o percentual de
    acréscimo, vale ele (sobre o valor inicial). Senão, a conta pelo valor: a Prefeitura costuma informar no
    campo "valor acrescido" o novo valor global; quando os dois coincidem, o acréscimo é a diferença para o
    valor anterior ao termo. Supressões não compensam acréscimos (art. 125): negativos contam como zero."""
    inicial = contrato.valor_inicial or Decimal(0)
    anterior = inicial
    resultado = []
    for a in sorted(contrato.aditivos, key=lambda x: (x.data is None, x.data, x.numero)):
        informado = a.valor_acrescimo or Decimal(0)
        declarado = percentual_acrescimo_declarado(a.descricao) if informado else None
        if declarado is not None:
            efetivo, criterio = (inicial * declarado / 100).quantize(Decimal("0.01")), "percentual declarado"
        elif a.valor_global is not None and informado and informado == a.valor_global:
            efetivo, criterio = a.valor_global - anterior, "valor global"
        else:
            efetivo, criterio = informado, "valor acrescido"
        resultado.append((a, max(efetivo, Decimal(0)), criterio))
        # Só termo de acréscimo muda a referência: o de prazo costuma repetir o valor original do contrato.
        if informado and a.valor_global:
            anterior = a.valor_global
    return resultado


class AditivosExcessivos(Regra):
    codigo = "aditivos"
    nome = "Aditivos acima do limite legal"
    base_legal = "Lei 14.133/2021, art. 125"
    descricao = (f"A soma dos acréscimos por termos aditivos passa de {int(PARAMS['aditivo_max_pct'] * 100)}% "
                 "do valor inicial do contrato. Vale o percentual de acréscimo declarado no termo; sem ele, a conta "
                 "é feita pelo valor (quando o termo informa o novo valor global no lugar do acréscimo, conta só a "
                 "diferença). Prorrogações de prazo, reajustes e supressões não entram.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not contrato.aditivos or not contrato.valor_inicial:
            return None
        efetivos = acrescimos_efetivos(contrato)
        soma = sum((v for _, v, _ in efetivos), Decimal(0))
        pct = float(soma / contrato.valor_inicial)
        if pct <= PARAMS["aditivo_max_pct"]:
            return None
        return self.resultado(contrato, {
            "percentual": round(pct * 100, 1), "valor_inicial": fmt(contrato.valor_inicial),
            "soma_acrescimos": fmt(soma),
            "aditivos": [{"numero": a.numero, "valor": fmt(v), "criterio": criterio, "origem": a.origem,
                          "data": a.data.isoformat() if a.data else None} for a, v, criterio in efetivos],
        })
