"""Senado Federal: senadores do MA, projetos de autoria e cota parlamentar (CEAPS)."""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import date, datetime
from functools import partial
from typing import Callable

import click
import requests

from ...extensions import db
from ...models import DespesaParlamentar, Politico, Proposicao
from ..http import criar_sessao, get_json
from ..texto import dinheiro_br, digitos, normalizar

BASE = "https://legis.senado.leg.br/dadosabertos"
URL_LISTA = f"{BASE}/senador/lista/atual.json"
URL_PROCESSO = f"{BASE}/processo"
URL_CEAPS = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
URL_MATERIA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}"
TIPOS = ("PL", "PLP", "PEC")
PAUSA_PADRAO = 0.2


def _baixar_texto(sessao: requests.Session, url: str) -> str:
    resp = sessao.get(url, timeout=120)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    return resp.content.decode("latin-1")


def _data(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _lista_senadores(get: Callable, pausa: float, falhas: list) -> list[dict]:
    try:
        resp = get(URL_LISTA) or {}
    except requests.RequestException as exc:
        click.echo(f"  erro em {URL_LISTA}: {exc}")
        falhas.append(exc)
        return []
    if pausa:
        time.sleep(pausa)
    itens = ((resp.get("ListaParlamentarEmExercicio") or {}).get("Parlamentares") or {}).get("Parlamentar") or []
    if isinstance(itens, dict):  # com um só item a API devolve objeto em vez de lista
        itens = [itens]
    ident = [(i.get("IdentificacaoParlamentar") or {}) for i in itens]
    return [i for i in ident if i.get("UfParlamentar") == "MA" and _int(i.get("CodigoParlamentar"))]


def _upsert_politico(i: dict) -> Politico:
    id_senado = int(i["CodigoParlamentar"])
    p = Politico.query.filter_by(id_senado=id_senado).first() or Politico(id_senado=id_senado)
    p.cargo = "Senador"
    p.uf = "MA"
    p.nome = i.get("NomeCompletoParlamentar") or i.get("NomeParlamentar") or p.nome or f"Senador {id_senado}"
    p.nome_urna = i.get("NomeParlamentar")
    p.partido = i.get("SiglaPartidoParlamentar")
    p.foto_url = i.get("UrlFotoParlamentar")
    p.em_exercicio = True
    p.atualizar_busca()
    db.session.add(p)
    db.session.flush()
    return p


def _gravar_proposicoes(get: Callable, p: Politico, de: date, pausa: float) -> None:
    for sigla in TIPOS:
        try:
            itens = get(URL_PROCESSO, params={"codigoParlamentarAutor": p.id_senado, "sigla": sigla}) or []
        except requests.RequestException as exc:
            click.echo(f"  erro em /processo ({p.id_senado}, {sigla}): {exc}")
            continue
        if pausa:
            time.sleep(pausa)
        for it in itens:
            apresentada = _data(it.get("dataApresentacao"))
            codigo = _int(it.get("codigoMateria"))
            if codigo is None or not apresentada or apresentada < de:
                continue
            m = re.match(r"\s*([A-Za-z]+)\s+(\d+)/(\d{4})", it.get("identificacao") or "")
            pr = (Proposicao.query.filter_by(politico_id=p.id, casa="Senado", id_externo=codigo).first()
                  or Proposicao(politico_id=p.id, casa="Senado", id_externo=codigo))
            pr.sigla_tipo = m.group(1).upper() if m else sigla
            pr.numero = int(m.group(2)) if m else None
            pr.ano = int(m.group(3)) if m else None
            pr.ementa = it.get("ementa")
            pr.data_apresentacao = apresentada
            pr.url = URL_MATERIA.format(codigo=codigo)
            db.session.add(pr)


def _linhas_ceaps(texto: str):
    linhas = texto.splitlines()
    for n, linha in enumerate(linhas):  # a 1ª linha é "ULTIMA ATUALIZACAO", antes do cabeçalho
        if linha.lstrip('"').startswith("ANO;") or linha.startswith("ANO"):
            return csv.DictReader(io.StringIO("\n".join(linhas[n:])), delimiter=";")
    return iter(())


def _data_br(v: str | None) -> date | None:
    try:
        return datetime.strptime((v or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _gravar_ceaps(baixar_texto: Callable[[str], str], politicos: list[Politico], de: date, ate: date) -> None:
    por_nome = {normalizar(p.nome_urna): p for p in politicos if p.nome_urna}
    for ano in range(de.year, ate.year + 1):
        url = URL_CEAPS.format(ano=ano)
        try:
            texto = baixar_texto(url)
        except requests.RequestException as exc:
            click.echo(f"  erro em {url}: {exc}")
            continue
        for row in _linhas_ceaps(texto or ""):
            p = por_nome.get(normalizar(row.get("SENADOR")))
            if p is None:
                continue
            cod = str(row.get("COD_DOCUMENTO") or "").strip()
            valor = dinheiro_br(row.get("VALOR_REEMBOLSADO"))
            d = DespesaParlamentar.query.filter_by(politico_id=p.id, cod_documento=cod, valor=valor).first()
            d = d or DespesaParlamentar(politico_id=p.id, cod_documento=cod, valor=valor)
            d.ano = _int(row.get("ANO"))
            d.mes = _int(row.get("MES"))
            d.tipo = row.get("TIPO_DESPESA")
            d.fornecedor_nome = row.get("FORNECEDOR")
            d.documento = digitos(row.get("CNPJ_CPF"))
            d.url_documento = None
            db.session.add(d)
    db.session.commit()


def coletar_senado(de: date, ate: date, get: Callable | None = None,
                   baixar_texto: Callable[[str], str] | None = None,
                   pausa: float = PAUSA_PADRAO) -> int:
    """Senadores do MA com projetos e CEAPS. Retorna nº de senadores."""
    sessao = criar_sessao()
    get = get or partial(get_json, sessao, timeout=60)
    baixar_texto = baixar_texto or partial(_baixar_texto, sessao)
    falhas: list = []
    idents = _lista_senadores(get, pausa, falhas)
    politicos = []
    for i in idents:
        p = _upsert_politico(i)
        _gravar_proposicoes(get, p, de, pausa)
        db.session.commit()
        politicos.append(p)
    if politicos:
        _gravar_ceaps(baixar_texto, politicos, de, ate)
    if politicos and not falhas:  # lista incompleta ou vazia não prova que alguém saiu
        ids = {p.id_senado for p in politicos}
        for p in Politico.query.filter(Politico.id_senado.isnot(None)).all():
            if p.id_senado not in ids:
                p.em_exercicio = False
        db.session.commit()
    return len(politicos)
