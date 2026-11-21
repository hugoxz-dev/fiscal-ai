"""Recursos Pro de saída de dados: CSV e relatórios para impressão (reaproveitam as fichas públicas)."""
from datetime import datetime

from flask import Blueprint, Response, abort, render_template, request

from ..extensions import db
from ..models import Fornecedor
from ..services import exportacao as svc
from . import contratos, fornecedores, politicos
from ._acesso import pro_obrigatorio

bp = Blueprint("exportacao", __name__)


def _csv(texto: str, nome: str) -> Response:
    return Response(texto, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})


@bp.route("/contratos.csv")
@pro_obrigatorio
def contratos_csv():
    q, _ = contratos.filtrar_contratos(request.args)
    return _csv(svc.contratos_csv(q.all()), f"fiscal-ai-contratos-{datetime.now():%Y%m%d}.csv")


@bp.route("/fornecedores/<int:id>/alertas.csv")
@pro_obrigatorio
def alertas_csv(id):
    f = db.session.get(Fornecedor, id) or abort(404)
    return _csv(svc.alertas_csv(f), f"fiscal-ai-alertas-fornecedor-{f.id}.csv")


RELATORIOS = {
    "contrato": ("contrato_detalhe.html", contratos.contexto_detalhe),
    "fornecedor": ("fornecedor.html", fornecedores.contexto_detalhe),
    "politico": ("politico.html", politicos.contexto_detalhe),
}


@bp.route("/relatorio/<tipo>/<int:id>")
@pro_obrigatorio
def relatorio(tipo, id):
    if tipo not in RELATORIOS:
        abort(404)
    template, contexto = RELATORIOS[tipo]
    extra = {}
    if tipo == "politico":  # a ficha usa ajudantes registrados só no blueprint de políticos
        extra = {"foto_src": politicos._foto_src, "iniciais": politicos._iniciais}
    return render_template(template, layout="relatorio_base.html", gerado_em=datetime.now(), **extra, **contexto(id))
