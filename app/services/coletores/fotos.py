"""Fotos oficiais de candidatura (TSE) do prefeito e dos vereadores, guardadas em app/static/fotos/.

Deputados e senadores já trazem a foto da Câmara/Senado (foto_url absoluta).
"""
from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

from ...extensions import db
from ...models import Politico
from .zip_remoto import abrir_zip as abrir_zip_remoto

URL_FOTOS = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{ano}/fotos/foto_cand{ano}_MA_div.zip"
CARGOS = ("Prefeito", "Vereador")


def _sq_do_arquivo(nome: str) -> str | None:
    """'FMA100002092730_div.jpeg' -> '100002092730'."""
    if not nome.startswith("FMA") or "_" not in nome:
        return None
    return nome[3:nome.index("_")]


def coletar_fotos(destino: Path, abrir_zip: Callable[[str], zipfile.ZipFile] | None = None) -> int:
    """Baixa a foto de quem ainda não tem arquivo local. Retorna quantas fotos foram gravadas."""
    abrir_zip = abrir_zip or abrir_zip_remoto
    destino = Path(destino)
    pendentes = defaultdict(list)
    for p in Politico.query.filter(Politico.cargo.in_(CARGOS), Politico.sq_candidato.isnot(None),
                                   Politico.ano_eleicao.isnot(None)):
        arquivo = destino / f"{p.sq_candidato}.jpg"
        if p.foto_url == f"fotos/{arquivo.name}" and arquivo.exists():
            continue
        pendentes[p.ano_eleicao].append(p)

    gravadas = 0
    for ano, politicos in pendentes.items():
        try:
            zf = abrir_zip(URL_FOTOS.format(ano=ano))
        except KeyError:
            continue
        membros = {_sq_do_arquivo(n): n for n in zf.namelist()}
        destino.mkdir(parents=True, exist_ok=True)
        for p in politicos:
            membro = membros.get(p.sq_candidato)
            if not membro:
                continue
            (destino / f"{p.sq_candidato}.jpg").write_bytes(zf.read(membro))
            p.foto_url = f"fotos/{p.sq_candidato}.jpg"
            gravadas += 1
    db.session.commit()
    return gravadas
