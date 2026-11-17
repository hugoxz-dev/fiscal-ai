"""Coletor do Diário Oficial do Município de São Luís (diariooficial.saoluis.ma.gov.br).

O portal tem dois acervos, ambos listados em /api/portal/editions/archive (público):
  - "legacy": edições em PDF (até 2026) -> texto via pdfplumber;
  - "digital": edições novas, já separadas em matérias (/api/portal/editions/{id}/matters).
Cada publicação termina com "Código identificador: <uuid>", usado para separar o texto.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Callable

import click
import pdfplumber
import requests
from bs4 import BeautifulSoup
from flask import current_app

from ...extensions import db
from ...models import Aditivo, Contrato, ExtratoDiario, Fornecedor, PublicacaoDiario
from ..http import criar_sessao, get_json

BASE = "https://diariooficial.saoluis.ma.gov.br"
LIMITE_PAGINA = 100
TOLERANCIA_VALOR = Decimal("0.01")  # 1%

_FIM_PUBLICACAO = re.compile(r"Código identificador:\s*\S+")
_CABECALHO = re.compile(
    r"^[ \t]*("
    r"EXTRATO\b"
    r"|RATIFICA\S*\b.*INEXIGIBILIDADE"
    r"|DISPENSA\b"
    r"|INEXIGIBILIDADE\b"
    r"|(?:[A-ZÀ-Ý0-9ºª°]+\s+)?TERMO ADITIVO\b"
    r").*$",
    re.MULTILINE,
)
_SUFIXOS = re.compile(r"\b(LTDA|ME|EPP|EIRELI|SA|S A|MEI|SS|SOCIEDADE SIMPLES)\b")


def eh_cabecalho_extrato(linha: str) -> bool:
    return bool(_CABECALHO.match(linha)) and "...." not in linha


def segmentar_extratos(texto: str) -> list[str]:
    """Separa o texto em publicações e devolve só as que são extratos de contratação/aditivo."""
    blocos = []
    for parte in _FIM_PUBLICACAO.split(texto):
        for m in _CABECALHO.finditer(parte):
            if "...." in m.group(0):
                continue  # linha do sumário
            bloco = parte[m.start():].strip()
            bloco = re.sub(r"\n?Publicado por:.*$", "", bloco, flags=re.DOTALL).strip()
            if len(bloco) >= 80:
                blocos.append(bloco)
            break
    return blocos


def _normalizar_nome(nome: str | None) -> str:
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = _SUFIXOS.sub(" ", s)
    return " ".join(s.split())


def _mesmo_fornecedor(extrato: ExtratoDiario, f: Fornecedor) -> bool:
    if extrato.documento_fornecedor:
        return extrato.documento_fornecedor == f.documento
    a, b = _normalizar_nome(extrato.nome_fornecedor), _normalizar_nome(f.nome)
    if len(a) < 6 or len(b) < 6:
        return False
    return a == b or a in b or b in a


def vincular_extratos() -> int:
    """Liga extratos a contratos do PNCP. Extratos de aditivo viram Aditivo(origem='diario')."""
    vinculados = 0
    contratos = Contrato.query.all()
    for e in ExtratoDiario.query.filter(ExtratoDiario.contrato_id.is_(None)).all():
        candidatos = [c for c in contratos if _mesmo_fornecedor(e, c.fornecedor)]
        if e.tipo == "aditivo":
            if len(candidatos) != 1 or e.valor is None:
                continue
            c = candidatos[0]
            numero = f"DOM-{e.id}"
            if not any(a.numero == numero and a.origem == "diario" for a in c.aditivos):
                c.aditivos.append(Aditivo(numero=numero, valor_acrescimo=e.valor,
                                          data=e.publicacao.data_edicao, origem="diario"))
        elif e.tipo in ("contrato", "dispensa", "inexigibilidade") and e.valor is not None:
            candidatos = [c for c in candidatos if c.valor_global and
                          abs(e.valor - c.valor_global) <= c.valor_global * TOLERANCIA_VALOR]
            if len(candidatos) != 1:
                continue
            c = candidatos[0]
        else:
            continue
        e.contrato = c
        vinculados += 1
    db.session.commit()
    return vinculados


def listar_edicoes(de: date, ate: date, get: Callable | None = None) -> list[dict]:
    """Edições do acervo com data entre `de` e `ate` (o acervo vem do mais recente ao mais antigo)."""
    get = get or partial(get_json, criar_sessao(), timeout=60)
    edicoes, pagina = [], 1
    while True:
        resp = get(f"{BASE}/api/portal/editions/archive", params={"page": pagina, "limit": LIMITE_PAGINA}) or {}
        itens = resp.get("editions") or []
        for e in itens:
            data_ed = date.fromisoformat(e["edition_date"][:10])
            if de <= data_ed <= ate:
                url = e.get("pdf_download_url") or f"/api/editions/{e['id']}/pdf"
                edicoes.append({"id": e["id"], "fonte": e.get("source", "legacy"), "data_edicao": data_ed,
                                "numero_edicao": e.get("edition_number"), "url_pdf": BASE + url})
        if not itens or date.fromisoformat(itens[-1]["edition_date"][:10]) < de \
                or pagina >= (resp.get("total_pages") or 1):
            return edicoes
        pagina += 1


def extrair_texto_pdf(caminho: Path) -> str:
    with pdfplumber.open(caminho) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _html_para_texto(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text("\n").strip()


def texto_da_edicao(edicao: dict, get: Callable, pasta: Path) -> str:
    if edicao["fonte"] == "digital":
        materias = (get(f"{BASE}/api/portal/editions/{edicao['id']}/matters") or {}).get("matters") or []
        return "\n".join(f"{m.get('title', '')}\n{_html_para_texto(m.get('content'))}\n"
                         f"Código identificador: materia-{m.get('id')}" for m in materias)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{edicao['fonte']}-{edicao['id']}.pdf"
    if not arquivo.exists():
        # o site bloqueia o User-Agent padrão "python-requests"; a sessão usa o do projeto
        resp = criar_sessao().get(edicao["url_pdf"], timeout=180)
        resp.raise_for_status()
        arquivo.write_bytes(resp.content)
    return extrair_texto_pdf(arquivo)


def coletar_diario(de: date, ate: date, llm, get: Callable | None = None) -> int:
    """Baixa edições, separa extratos e usa o LLM para estruturá-los. Retorna nº de extratos gravados."""
    get = get or partial(get_json, criar_sessao(), timeout=60)
    pasta = Path(current_app.config["DATA_DIR"]) / "diario"
    gravados = 0
    for ed in listar_edicoes(de, ate, get=get):
        pub = PublicacaoDiario.query.filter_by(url_pdf=ed["url_pdf"]).first()
        if pub is not None and pub.processado:
            continue
        if pub is None:
            try:
                texto = texto_da_edicao(ed, get, pasta)
            except (requests.RequestException, OSError, ValueError) as exc:
                click.echo(f"  falha ao obter {ed['numero_edicao']}: {exc}")
                continue
            pub = PublicacaoDiario(url_pdf=ed["url_pdf"], data_edicao=ed["data_edicao"],
                                   numero_edicao=(ed["numero_edicao"] or "")[:30], texto=texto)
            db.session.add(pub)
        blocos = segmentar_extratos(pub.texto or "")
        dados = [llm.extrair_extrato(b) for b in blocos]
        if any(d is None for d in dados):
            pub.processado = False  # LLM indisponível: tenta de novo na próxima coleta
        else:
            for bloco, d in zip(blocos, dados):
                pub.extratos.append(ExtratoDiario(trecho=bloco, **d))
            pub.processado = True
            gravados += len(blocos)
        db.session.commit()
        situacao = "" if pub.processado else " (aguardando LLM)"
        click.echo(f"  {ed['data_edicao']:%d/%m/%Y} {ed['numero_edicao']}: {len(blocos)} extratos{situacao}")
    vincular_extratos()
    return gravados
