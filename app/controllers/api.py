"""API v1 somente leitura do plano Pro/Institucional. Autenticação pelo cabeçalho X-API-Key."""
from flask import Blueprint, abort, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from ..extensions import db
from ..models import Alerta, Contrato, Fornecedor
from ..services import api_chaves, contas, exportacao
from .contratos import filtrar_contratos

bp = Blueprint("api", __name__)
POR_PAGINA_MAX = 100


def _erro(status: int, mensagem: str):
    r = jsonify({"erro": mensagem})
    r.status_code = status
    return r


@bp.route("/api")
def docs():
    return render_template("api_docs.html", limite=api_chaves.LIMITE_DIARIO)


@bp.before_request
def _autenticar():
    if not request.path.startswith("/api/v1/"):
        return None
    chave = api_chaves.validar(request.headers.get("X-API-Key"))
    if chave is None:
        return _erro(401, "chave de API ausente ou inválida")
    assinatura = contas.assinatura_ativa(chave.usuario)
    if assinatura is None:
        return _erro(403, "assinatura Pro inativa")
    ilimitado = assinatura.plano == "institucional"
    if not ilimitado and api_chaves.chamadas_hoje(chave) >= api_chaves.LIMITE_DIARIO:
        return _erro(429, f"limite diário de {api_chaves.LIMITE_DIARIO} chamadas atingido")
    g.api_chamadas = api_chaves.registrar_uso(chave)
    g.api_limite = "ilimitado" if ilimitado else str(api_chaves.LIMITE_DIARIO)
    return None


@bp.after_request
def _cabecalhos(resposta):
    if "api_limite" in g:
        resposta.headers["X-Limite-Diario"] = g.api_limite
        resposta.headers["X-Chamadas-Hoje"] = str(g.api_chamadas)
        g.pop("api_limite")
    return resposta


@bp.errorhandler(HTTPException)
def _http(e):
    if request.path.startswith("/api/v1/"):
        return _erro(e.code, e.description if e.code != 404 else "não encontrado")
    return e


def _paginar(q):
    try:
        pagina = max(int(request.args.get("pagina", 1)), 1)
        por_pagina = min(max(int(request.args.get("por_pagina", 25)), 1), POR_PAGINA_MAX)
    except ValueError:
        abort(400, "pagina e por_pagina devem ser números")
    p = q.paginate(page=pagina, per_page=por_pagina, error_out=False)
    return p, {"pagina": pagina, "por_pagina": por_pagina, "total": p.total}


@bp.route("/api/v1/contratos")
def contratos():
    q, _ = filtrar_contratos(request.args)
    p, meta = _paginar(q)
    return jsonify({**meta, "itens": [exportacao.contrato_dict(c) for c in p.items]})


@bp.route("/api/v1/contratos/<int:id>")
def contrato(id):
    c = db.session.get(Contrato, id) or abort(404)
    return jsonify(exportacao.contrato_dict(c, com_alertas=True))


@bp.route("/api/v1/fornecedores/<int:id>")
def fornecedor(id):
    f = db.session.get(Fornecedor, id) or abort(404)
    return jsonify(exportacao.fornecedor_dict(f))


@bp.route("/api/v1/alertas")
def alertas():
    q = Alerta.query
    if request.args.get("regra"):
        q = q.filter(Alerta.regra_codigo == request.args["regra"])
    p, meta = _paginar(q.order_by(Alerta.criado_em.desc(), Alerta.id.desc()))
    return jsonify({**meta, "itens": [{"contrato_id": a.contrato_id, **exportacao.alerta_dict(a)} for a in p.items]})
