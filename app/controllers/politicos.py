from collections import OrderedDict, defaultdict
from decimal import Decimal

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from ..extensions import db
from ..models import Politico
from ..services.ligacoes import contar_ligacoes, ligacoes_do_politico, resumo_fornecedor
from ..services.texto import normalizar

bp = Blueprint("politicos", __name__)

CARGOS = ["Prefeito", "Senador", "Deputado Federal", "Vereador"]
COM_MANDATO_FEDERAL = ("Deputado Federal", "Senador")


def _buscar(q: str):
    """Critério único da busca: nome normalizado contido em nome_busca, só quem está em exercício."""
    q = normalizar(q or "")
    if len(q) < 2:
        return None
    seguro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return (Politico.query.filter(Politico.em_exercicio.is_(True),
                                  Politico.nome_busca.like(f"%{seguro}%", escape="\\"))
            .order_by(Politico.nome_urna, Politico.nome))


def _nome_exibido(p):
    return p.nome_urna or p.nome


def _foto_src(p) -> str | None:
    """Foto da Câmara/Senado (URL absoluta) ou do TSE baixada em static/fotos (caminho relativo)."""
    if not p.foto_url:
        return None
    if p.foto_url.startswith(("http://", "https://")):
        return p.foto_url
    return url_for("static", filename=p.foto_url)


def _iniciais(p) -> str:
    partes = _nome_exibido(p).split()
    return "".join(x[0] for x in (partes[:1] + partes[1:][-1:])).upper()


@bp.context_processor
def _ajudantes_de_foto():
    return {"foto_src": _foto_src, "iniciais": _iniciais}


@bp.route("/politicos")
def lista():
    q = request.args.get("q", "").strip()
    consulta = _buscar(q)
    if consulta is None:  # menos de 2 caracteres: lista tudo
        consulta = (Politico.query.filter(Politico.em_exercicio.is_(True))
                    .order_by(Politico.nome_urna, Politico.nome))
    grupos = OrderedDict((c, []) for c in CARGOS)
    for p in consulta.all():
        if p.cargo in grupos:
            grupos[p.cargo].append(p)
    grupos = OrderedDict((c, ps) for c, ps in grupos.items() if ps)
    return render_template("politicos.html", q=q, grupos=grupos, ligacoes=contar_ligacoes(),
                           nome_exibido=_nome_exibido)


@bp.route("/politicos/busca.json")
def busca():
    consulta = _buscar(request.args.get("q", ""))
    if consulta is None:
        return jsonify([])
    return jsonify([{"id": p.id, "nome": p.nome, "nome_urna": _nome_exibido(p), "cargo": p.cargo,
                     "partido": p.partido, "url": url_for("politicos.detalhe", id=p.id)}
                    for p in consulta.limit(10).all()])


def _agregar_doadores(doacoes):
    """Agrupa por nome normalizado; nunca expõe o documento."""
    grupos: dict[str, dict] = {}
    for d in doacoes:
        g = grupos.setdefault(d.nome_norm or normalizar(d.nome or ""),
                              {"nome": d.nome or "—", "qtd": 0, "total": Decimal("0")})
        g["qtd"] += 1
        g["total"] += d.valor or Decimal("0")
    return sorted(grupos.values(), key=lambda g: -g["total"])


@bp.route("/politicos/<int:id>")
def detalhe(id):
    p = db.session.get(Politico, id) or abort(404)
    ligs = ligacoes_do_politico(p)
    resumos = {l.fornecedor.id: resumo_fornecedor(l.fornecedor) for l in ligs}
    bens = sorted(p.bens, key=lambda b: -(b.valor or 0))
    diretas = _agregar_doadores([d for d in p.doacoes if not d.originario])
    originarias = _agregar_doadores([d for d in p.doacoes if d.originario])
    cota: dict[str, Decimal] = defaultdict(Decimal)
    for d in p.despesas:
        cota[d.tipo or "Outros"] += d.valor or Decimal("0")
    return render_template(
        "politico.html", p=p, nome_exibido=_nome_exibido(p),
        confirmadas=[l for l in ligs if l.confirmada], so_nome=[l for l in ligs if not l.confirmada],
        resumos=resumos, bens=bens, total_bens=sum((b.valor or 0 for b in bens), Decimal("0")),
        doadores=diretas[:50], total_doadores=sum((g["total"] for g in diretas), Decimal("0")),
        originarios=originarias[:50],
        emendas=sorted(p.emendas, key=lambda e: (-(e.ano or 0), -(e.valor_empenhado or 0))),
        proposicoes=sorted(p.proposicoes, key=lambda x: (x.data_apresentacao is not None, x.data_apresentacao),
                           reverse=True),
        cota=sorted(cota.items(), key=lambda x: -x[1]), total_cota=sum(cota.values(), Decimal("0")),
        federal=p.cargo in COM_MANDATO_FEDERAL)
