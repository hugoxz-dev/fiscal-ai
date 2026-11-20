"""Câmara dos Deputados: deputados do MA, cota parlamentar e projetos de autoria."""
from __future__ import annotations

import time
from datetime import date
from functools import partial
from typing import Callable

import click
import requests

from ...extensions import db
from ...models import DespesaParlamentar, Politico, Proposicao
from ..http import criar_sessao, get_json
from ..texto import cpf_valido, dinheiro_br, digitos

BASE = "https://dadosabertos.camara.leg.br/api/v2"
PAUSA_PADRAO = 0.2


def _data(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def _paginas(get: Callable, url: str, params: dict, pausa: float, falhas: list | None = None):
    pagina = 1
    while True:
        try:
            resp = get(url, params={**params, "pagina": pagina})
        except requests.RequestException as exc:
            click.echo(f"  erro em {url} página {pagina}: {exc}")
            if falhas is not None:
                falhas.append(exc)
            return
        if pausa:
            time.sleep(pausa)
        itens = (resp or {}).get("dados") or []
        if not itens:
            return
        yield from itens
        pagina += 1


def _upsert_politico(get: Callable, id_camara: int, pausa: float) -> Politico | None:
    try:
        resp = get(f"{BASE}/deputados/{id_camara}") or {}
    except requests.RequestException as exc:
        click.echo(f"  erro em /deputados/{id_camara}: {exc}")
        return None
    if pausa:
        time.sleep(pausa)
    d = resp.get("dados")
    if not d:
        return None
    status = d.get("ultimoStatus") or {}
    p = Politico.query.filter_by(id_camara=id_camara).first() or Politico(id_camara=id_camara)
    p.cargo = "Deputado Federal"
    p.uf = "MA"
    p.nome = d.get("nomeCivil") or status.get("nome") or p.nome or f"Deputado {id_camara}"
    p.nome_urna = status.get("nome")
    p.cpf = cpf_valido(d.get("cpf")) or p.cpf
    p.partido = status.get("siglaPartido")
    p.foto_url = status.get("urlFoto")
    p.em_exercicio = True
    p.ano_eleicao = 2022
    p.atualizar_busca()
    db.session.add(p)
    db.session.flush()
    return p


def _gravar_despesas(get: Callable, p: Politico, de: date, ate: date, pausa: float) -> None:
    for ano in range(de.year, ate.year + 1):
        for it in _paginas(get, f"{BASE}/deputados/{p.id_camara}/despesas",
                           {"ano": ano, "itens": 100}, pausa):
            cod = str(it.get("codDocumento") or "")
            valor = dinheiro_br(it.get("valorLiquido"))
            d = DespesaParlamentar.query.filter_by(politico_id=p.id, cod_documento=cod, valor=valor).first()
            d = d or DespesaParlamentar(politico_id=p.id, cod_documento=cod, valor=valor)
            d.ano = it.get("ano")
            d.mes = it.get("mes")
            d.tipo = it.get("tipoDespesa")
            d.fornecedor_nome = it.get("nomeFornecedor")
            d.documento = digitos(it.get("cnpjCpfFornecedor"))
            d.url_documento = it.get("urlDocumento")
            db.session.add(d)


def _gravar_proposicoes(get: Callable, p: Politico, de: date, pausa: float) -> None:
    params = {"idDeputadoAutor": p.id_camara, "siglaTipo": "PL,PLP,PEC",
              "dataApresentacaoInicio": de.isoformat(), "itens": 100}
    for it in _paginas(get, f"{BASE}/proposicoes", params, pausa):
        pr = (Proposicao.query.filter_by(politico_id=p.id, casa="Câmara", id_externo=it["id"]).first()
              or Proposicao(politico_id=p.id, casa="Câmara", id_externo=it["id"]))
        pr.sigla_tipo = it.get("siglaTipo")
        pr.numero = it.get("numero")
        pr.ano = it.get("ano")
        pr.ementa = it.get("ementa")
        pr.data_apresentacao = _data(it.get("dataApresentacao"))
        pr.url = f"https://www.camara.leg.br/propostas-legislativas/{it['id']}"
        db.session.add(pr)


def coletar_camara(de: date, ate: date, get: Callable | None = None, pausa: float = PAUSA_PADRAO) -> int:
    """Deputados do MA com cota e projetos. Retorna nº de deputados."""
    get = get or partial(get_json, criar_sessao(), timeout=60)
    falhas: list = []
    lista = _paginas(get, f"{BASE}/deputados", {"siglaUf": "MA", "itens": 100}, pausa, falhas)
    ids = [x["id"] for x in lista]
    for id_camara in ids:
        p = _upsert_politico(get, id_camara, pausa)
        if p is None:
            continue
        _gravar_despesas(get, p, de, ate, pausa)
        _gravar_proposicoes(get, p, de, pausa)
        db.session.commit()
    if ids and not falhas:  # lista incompleta ou vazia não prova que alguém saiu
        for p in Politico.query.filter(Politico.id_camara.isnot(None)).all():
            if p.id_camara not in ids:
                p.em_exercicio = False
        db.session.commit()
    return len(ids)
