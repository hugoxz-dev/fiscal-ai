from collections import defaultdict

from flask import Blueprint, abort, render_template

from ..extensions import db
from ..models import Contrato, Fornecedor, Sancao
from ..services.ligacoes import ligacoes_do_fornecedor

bp = Blueprint("fornecedores", __name__)


@bp.route("/fornecedores/<int:id>")
def detalhe(id):
    # rota pelo id interno: o CPF de pessoa física nunca vai para a URL
    return render_template("fornecedor.html", **contexto_detalhe(id))


def contexto_detalhe(id: int) -> dict:
    f = db.session.get(Fornecedor, id) or abort(404)
    sancoes = Sancao.query.filter_by(documento=f.documento).order_by(Sancao.data_inicio.desc()).all()
    contratos = sorted(f.contratos, key=lambda c: -c.score)
    # participação do fornecedor no total contratado por órgão e ano
    concentracao = []
    for (orgao, ano), valor in _somas(f).items():
        total = sum(c.valor_global or 0 for c in Contrato.query.filter_by(orgao_id=orgao.id)
                    if c.data_assinatura and c.data_assinatura.year == ano)
        if total:
            concentracao.append({"orgao": orgao.razao_social, "ano": ano, "valor": valor, "total": total,
                                 "percentual": round(float(valor / total) * 100, 1)})
    ligacoes = ligacoes_do_fornecedor(f)
    return {"f": f, "sancoes": sancoes, "contratos": contratos, "concentracao": concentracao,
            "ligacoes_confirmadas": [l for l in ligacoes if l.confirmada],
            "ligacoes_so_nome": [l for l in ligacoes if not l.confirmada]}


def _somas(f):
    somas = defaultdict(int)
    for c in f.contratos:
        if c.data_assinatura and c.valor_global:
            somas[(c.orgao, c.data_assinatura.year)] += c.valor_global
    return somas
