"""Portal da Transparência: sanções (CEIS/CNEP) e convênios federais com o município."""
from __future__ import annotations

import time
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Callable

import click
import requests
from flask import current_app

from ...extensions import db
from ...models import Convenio, Fornecedor, Orgao, Sancao
from ..http import criar_sessao, get_json

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
PAUSA_PADRAO = 0.7  # limite da API: ~90 requisições por minuto


def _data(v: str | None) -> date | None:
    if not v:
        return None
    if "/" in v:
        return datetime.strptime(v[:10], "%d/%m/%Y").date()
    return date.fromisoformat(v[:10])


def _digitos(v: str | None) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _sem_acento(v: str) -> str:
    return unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().upper()


def parse_sancao(item: dict, cadastro: str) -> dict:
    tipo = (item.get("tipoSancao") or {}).get("descricaoResumida") or ""
    return {
        "documento": _digitos((item.get("sancionado") or {}).get("codigoFormatado")),
        "cadastro": cadastro,
        "data_inicio": _data(item.get("dataInicioSancao")),
        "data_fim": _data(item.get("dataFimSancao")),
        "orgao_sancionador": (item.get("orgaoSancionador") or {}).get("nome"),
        "descricao": tipo,
    }


def parse_convenio(item: dict, cnpjs_municipais: set[str] | None = None) -> dict:
    conv = item.get("convenente") or {}
    cnpj = _digitos(conv.get("cnpjFormatado"))
    municipal = cnpj in (cnpjs_municipais or set()) or "MUNICIP" in _sem_acento(conv.get("nome") or "")
    dim = item.get("dimConvenio") or {}
    valor = item.get("valor")
    return {
        "numero": str(dim.get("numero")),
        "orgao_concedente": (item.get("orgao") or {}).get("nome"),
        "objeto": dim.get("objeto"),
        "valor": None if valor is None else Decimal(str(valor)).quantize(Decimal("0.01")),
        "data_inicio": _data(item.get("dataInicioVigencia")),
        "convenente_municipal": municipal,
    }


def _get_padrao(get: Callable | None) -> Callable | None:
    chave = current_app.config.get("TRANSPARENCIA_API_KEY")
    if not chave:
        click.echo("TRANSPARENCIA_API_KEY não configurada — pulando")
        return None
    return get or partial(get_json, criar_sessao({"chave-api-dados": chave}), timeout=60)


def _paginas(get: Callable, url: str, params: dict, pausa: float):
    pagina = 1
    while True:
        try:
            itens = get(url, params={**params, "pagina": pagina})
        except requests.RequestException as exc:
            click.echo(f"  erro em {url} página {pagina}: {exc}")
            return
        if pausa:
            time.sleep(pausa)
        if not itens:
            return
        yield from itens
        pagina += 1


def coletar_sancoes(get: Callable | None = None, pausa: float = PAUSA_PADRAO) -> int:
    """Consulta CEIS e CNEP para cada fornecedor PJ. Retorna nº de sanções novas."""
    get = _get_padrao(get)
    if get is None:
        return 0
    novas = 0
    for f in Fornecedor.query.filter_by(tipo="PJ").all():
        for cadastro in ("CEIS", "CNEP"):
            url = f"{BASE}/{cadastro.lower()}"
            for item in _paginas(get, url, {"codigoSancionado": f.documento}, pausa):
                d = parse_sancao(item, cadastro)
                if d["documento"] != f.documento:
                    continue
                existe = Sancao.query.filter_by(documento=d["documento"], cadastro=cadastro,
                                                data_inicio=d["data_inicio"]).first()
                if existe is None:
                    db.session.add(Sancao(**d))
                    novas += 1
        db.session.commit()
    return novas


def coletar_convenios(de: date, ate: date, ibge: str, get: Callable | None = None,
                      pausa: float = PAUSA_PADRAO) -> int:
    """Convênios federais cujo convenente é a Prefeitura ou entidade municipal. Retorna nº gravados."""
    get = _get_padrao(get)
    if get is None:
        return 0
    cnpjs = {o.cnpj for o in Orgao.query.filter_by(esfera="M")}
    params = {"codigoIBGE": ibge, "dataInicial": de.strftime("%d/%m/%Y"), "dataFinal": ate.strftime("%d/%m/%Y")}
    gravados = 0
    for item in _paginas(get, f"{BASE}/convenios", params, pausa):
        d = parse_convenio(item, cnpjs)
        if not d.pop("convenente_municipal"):
            continue
        c = Convenio.query.filter_by(numero=d["numero"]).first() or Convenio(numero=d["numero"])
        for campo, valor in d.items():
            setattr(c, campo, valor)
        db.session.add(c)
        gravados += 1
    db.session.commit()
    return gravados
