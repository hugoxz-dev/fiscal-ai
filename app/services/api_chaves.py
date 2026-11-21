"""Chaves da API (plano Pro/Institucional). Só o hash sha256 é guardado; a chave completa aparece uma vez."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime

from ..extensions import db
from ..models import ChaveApi, UsoApi, Usuario

LIMITE_DIARIO = 1000


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def revogar(u: Usuario) -> None:
    for k in u.chaves:
        if k.revogada_em is None:
            k.revogada_em = datetime.now()
    db.session.commit()


def gerar(u: Usuario) -> str:
    revogar(u)
    chave = "fai_" + secrets.token_urlsafe(32)
    u.chaves.append(ChaveApi(prefixo=chave[:8], chave_hash=_hash(chave)))
    db.session.commit()
    return chave


def ativa(u: Usuario) -> ChaveApi | None:
    return next((k for k in u.chaves if k.revogada_em is None), None)


def validar(texto: str | None) -> ChaveApi | None:
    if not texto:
        return None
    return ChaveApi.query.filter_by(chave_hash=_hash(texto.strip()), revogada_em=None).first()


def chamadas_hoje(chave: ChaveApi, hoje: date | None = None) -> int:
    uso = UsoApi.query.filter_by(chave_id=chave.id, dia=hoje or date.today()).first()
    return uso.chamadas if uso else 0


def registrar_uso(chave: ChaveApi, hoje: date | None = None) -> int:
    hoje = hoje or date.today()
    uso = UsoApi.query.filter_by(chave_id=chave.id, dia=hoje).first()
    if uso is None:
        uso = UsoApi(chave_id=chave.id, dia=hoje, chamadas=0)
        db.session.add(uso)
    uso.chamadas += 1
    db.session.commit()
    return uso.chamadas
