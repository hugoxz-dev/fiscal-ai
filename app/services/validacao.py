"""Validação manual dos alertas (para o capítulo de resultados do TCC).

1. `sortear_alertas` tira uma amostra aleatória e reprodutível (semente) de cada regra.
2. `gravar_amostra` gera uma planilha CSV que abre direto no Excel; a pessoa confere cada alerta
   na fonte e preenche a coluna "veredito" com: acerto, falso positivo ou inconclusivo.
3. `resumir` lê a planilha preenchida e calcula a precisão de cada regra:
   acertos / (acertos + falsos positivos). Inconclusivos e pendentes não entram na conta.
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

from ..models import Alerta
from ..views._filtros import ROTULOS_EVIDENCIA, cnpj, data_br, evidencia_valor, moeda
from .analisador import REGRAS

COLUNAS = ["alerta_id", "regra", "nome_regra", "contrato_id", "score", "objeto", "fornecedor", "valor",
           "assinatura", "evidencias", "painel", "fonte", "veredito", "observacao"]
VEREDITOS = {"a": "acerto", "f": "falso positivo", "i": "inconclusivo"}
NOMES = {cls.codigo: cls.nome for cls in REGRAS}
ORDEM = {cls.codigo: i for i, cls in enumerate(REGRAS)}


class ErroValidacao(ValueError):
    pass


def sortear_alertas(por_regra: int = 5, semente: int = 42) -> list[Alerta]:
    """Até `por_regra` alertas de cada regra, sorteados com semente fixa (mesma amostra a cada execução)."""
    grupos = defaultdict(list)
    for a in Alerta.query.order_by(Alerta.id):
        grupos[a.regra_codigo].append(a)
    sorteio = random.Random(semente)
    amostra = []
    for codigo in sorted(grupos, key=lambda c: ORDEM.get(c, 99)):
        alertas = grupos[codigo]
        escolhidos = alertas if len(alertas) <= por_regra else sorteio.sample(alertas, por_regra)
        amostra.extend(sorted(escolhidos, key=lambda a: a.id))
    return amostra


def _evidencias(evidencia: dict) -> str:
    return "\n".join(f"{ROTULOS_EVIDENCIA.get(k, k)}: {evidencia_valor(k, v)}"
                     for k, v in (evidencia or {}).items() if k != "link" and v not in (None, "", []))


def _linha(a: Alerta, base_url: str) -> dict:
    c, f = a.contrato, a.contrato.fornecedor
    return {
        "alerta_id": a.id, "regra": a.regra_codigo, "nome_regra": NOMES.get(a.regra_codigo, a.regra_codigo),
        "contrato_id": c.id, "score": c.score, "objeto": c.objeto or "",
        "fornecedor": f"{f.nome} ({cnpj(f.documento)})" if f else "",
        "valor": moeda(c.valor_global), "assinatura": data_br(c.data_assinatura),
        "evidencias": _evidencias(a.evidencia), "painel": f"{base_url.rstrip('/')}/contratos/{c.id}",
        "fonte": c.link_pncp or "", "veredito": "", "observacao": "",
    }


def gravar_amostra(caminho, alertas: list[Alerta], base_url: str) -> None:
    """CSV com ';' e BOM UTF-8 — o formato que o Excel em português abre sem assistente."""
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=";")
        w.writeheader()
        w.writerows(_linha(a, base_url) for a in alertas)


def _veredito(texto: str, numero_linha: int) -> str | None:
    t = (texto or "").strip().lower()
    if not t:
        return None
    if t[0] in VEREDITOS and VEREDITOS[t[0]].startswith(t):
        return VEREDITOS[t[0]]
    raise ErroValidacao(f"linha {numero_linha}: veredito \"{texto.strip()}\" inválido — "
                        "use acerto, falso positivo ou inconclusivo (ou só a, f, i)")


def resumir(caminho) -> list[dict]:
    contagem = defaultdict(lambda: {"acerto": 0, "falso positivo": 0, "inconclusivo": 0, None: 0})
    with open(Path(caminho), encoding="utf-8-sig", newline="") as f:
        for n, linha in enumerate(csv.DictReader(f, delimiter=";"), start=2):  # linha 1 = cabeçalho
            contagem[linha["regra"]][_veredito(linha.get("veredito", ""), n)] += 1
    resumo = []
    for codigo in sorted(contagem, key=lambda c: ORDEM.get(c, 99)):
        k = contagem[codigo]
        decididos = k["acerto"] + k["falso positivo"]
        resumo.append({"regra": codigo, "nome": NOMES.get(codigo, codigo), "avaliados": sum(k.values()),
                       "acertos": k["acerto"], "falsos": k["falso positivo"], "inconclusivos": k["inconclusivo"],
                       "pendentes": k[None], "precisao": k["acerto"] / decididos if decididos else None})
    return resumo


def _pct(p: float | None) -> str:
    return "—" if p is None else f"{p * 100:.1f}%".replace(".", ",")


def tabela_markdown(resumo: list[dict]) -> str:
    linhas = ["| Regra | Avaliados | Acertos | Falsos positivos | Inconclusivos | Pendentes | Precisão |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for r in resumo:
        linhas.append(f"| {r['nome']} | {r['avaliados']} | {r['acertos']} | {r['falsos']} | "
                      f"{r['inconclusivos']} | {r['pendentes']} | {_pct(r['precisao'])} |")
    t = {k: sum(r[k] for r in resumo) for k in ("avaliados", "acertos", "falsos", "inconclusivos", "pendentes")}
    decididos = t["acertos"] + t["falsos"]
    linhas.append(f"| **Total** | {t['avaliados']} | {t['acertos']} | {t['falsos']} | {t['inconclusivos']} | "
                  f"{t['pendentes']} | {_pct(t['acertos'] / decididos if decididos else None)} |")
    return "\n".join(linhas)
