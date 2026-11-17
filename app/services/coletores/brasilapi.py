"""Enriquecimento de fornecedores PJ com dados públicos do CNPJ (BrasilAPI)."""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Callable

import requests

from ...extensions import db
from ...models import Fornecedor
from ..http import criar_sessao, get_json

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
            enriquecidos += 1
        f.enriquecido_em = datetime.now()
        db.session.commit()
        if pausa:
            time.sleep(pausa)
    return enriquecidos
