"""Enriquecimento de fornecedores PJ com dados públicos do CNPJ (BrasilAPI)."""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Callable

import requests

from ...extensions import db
from ...models import Fornecedor, Socio
from ..http import criar_sessao, get_json
from ..texto import cpf_meio, normalizar

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def parse_cnpj(d: dict) -> dict:
    abertura = d.get("data_inicio_atividade")
    capital = d.get("capital_social")
    return {
        "data_abertura": date.fromisoformat(abertura) if abertura else None,
        "capital_social": None if capital is None else Decimal(str(capital)).quantize(Decimal("0.01")),
        "cnae_codigo": str(d["cnae_fiscal"]) if d.get("cnae_fiscal") else None,
        "cnae_descricao": d.get("cnae_fiscal_descricao"),
        "situacao": d.get("descricao_situacao_cadastral"),
        "cnaes_secundarios": "; ".join(c["descricao"] for c in d.get("cnaes_secundarios") or []
                                       if c.get("descricao")) or None,
        "natureza_juridica": str(d["codigo_natureza_juridica"]) if d.get("codigo_natureza_juridica") else None,
    }


def parse_socios(d: dict) -> list[dict]:
    """Quadro societário (QSA). Mesmo nome repetido: fica o primeiro."""
    vistos: set[str] = set()
    socios = []
    for q in d.get("qsa") or []:
        nome = (q.get("nome_socio") or "").strip()
        if not nome or nome in vistos:
            continue
        vistos.add(nome)
        entrada = q.get("data_entrada_sociedade")
        socios.append({
            "nome": nome,
            "nome_norm": normalizar(nome),
            "cpf_meio": cpf_meio(q.get("cnpj_cpf_do_socio")),
            "qualificacao": q.get("qualificacao_socio"),
            "data_entrada": date.fromisoformat(entrada) if entrada else None,
        })
    return socios


def gravar_socios(f: Fornecedor, socios: list[dict]) -> int:
    """Substitui os sócios do fornecedor (apaga e insere). O commit fica com quem chama."""
    Socio.query.filter_by(fornecedor_id=f.id).delete()
    db.session.expire(f, ["socios"])
    for s in socios:
        db.session.add(Socio(fornecedor_id=f.id, **s))
    db.session.flush()
    return len(socios)


def enriquecer_fornecedores(get: Callable | None = None, limite: int | None = None,
                            pausa: float = 0.5) -> int:
    """Consulta a BrasilAPI para fornecedores PJ ainda não enriquecidos. Retorna quantos receberam dados."""
    if get is None:
        get = partial(get_json, criar_sessao(), timeout=30)
    pendentes = Fornecedor.query.filter_by(tipo="PJ", enriquecido_em=None).limit(limite).all()
    enriquecidos = 0
    for f in pendentes:
        try:
            dados = get(URL.format(cnpj=f.documento))
        except requests.RequestException:
            continue  # falha transitória: tenta de novo na próxima coleta
        if dados:
            for campo, valor in parse_cnpj(dados).items():
                setattr(f, campo, valor)
            gravar_socios(f, parse_socios(dados))
            enriquecidos += 1
        f.enriquecido_em = datetime.now()
        db.session.commit()
        if pausa:
            time.sleep(pausa)
    return enriquecidos


def coletar_socios(get: Callable | None = None, pausa: float = 0.5) -> int:
    """Busca o QSA de fornecedores PJ já enriquecidos que ainda não têm nenhum sócio.
    Retorna quantos fornecedores receberam sócios."""
    if get is None:
        get = partial(get_json, criar_sessao(), timeout=30)
    pendentes = (Fornecedor.query.filter(Fornecedor.tipo == "PJ", Fornecedor.enriquecido_em.isnot(None),
                                         ~Fornecedor.socios.any()).all())
    gravados = 0
    for f in pendentes:
        try:
            dados = get(URL.format(cnpj=f.documento))
        except requests.RequestException:
            continue
        if dados and gravar_socios(f, parse_socios(dados)):
            gravados += 1
        db.session.commit()
        if pausa:
            time.sleep(pausa)
    return gravados
