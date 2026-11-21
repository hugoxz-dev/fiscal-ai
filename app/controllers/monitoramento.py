from flask import Blueprint, abort, redirect, render_template, request

from ..services import monitoramento as svc
from ._acesso import next_seguro, pro_obrigatorio, usuario_atual

bp = Blueprint("monitoramento", __name__)


def _alterar(acao, tipo: str, id: int):
    try:
        acao(usuario_atual(), tipo, id)
    except (LookupError, ValueError):
        abort(404)
    return redirect(next_seguro(request.form.get("next")))


@bp.route("/seguir/<tipo>/<int:id>", methods=["POST"])
@pro_obrigatorio
def seguir(tipo, id):
    return _alterar(svc.seguir, tipo, id)


@bp.route("/deixar/<tipo>/<int:id>", methods=["POST"])
@pro_obrigatorio
def deixar(tipo, id):
    if tipo not in svc.MODELOS:
        abort(404)
    return _alterar(svc.deixar, tipo, id)


@bp.route("/conta/monitoramento")
@pro_obrigatorio
def painel():
    u = usuario_atual()
    itens = svc.novidades(u)
    html = render_template("monitoramento.html", itens=itens, total=sum(len(i["contratos"]) + len(i["alertas"])
                                                                        for i in itens))
    svc.marcar_visita(u)  # depois de montar a página: o que foi mostrado agora deixa de ser novidade
    return html
