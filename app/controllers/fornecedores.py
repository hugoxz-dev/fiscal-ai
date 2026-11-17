from collections import defaultdict

from flask import Blueprint, abort, render_template

from ..models import Contrato, Fornecedor, Sancao

bp = Blueprint("fornecedores", __name__)


@bp.route("/fornecedores/<documento>")
def detalhe(documento):
    f = Fornecedor.query.filter_by(documento=documento).first() or abort(404)
    sancoes = Sancao.query.filter_by(documento=documento).order_by(Sancao.data_inicio.desc()).all()
    contratos = sorted(f.contratos, key=lambda c: -c.score)
    # participação do fornecedor no total contratado por órgão e ano
    concentracao = []
    for (orgao, ano), valor in _somas(f).items():
        total = sum(c.valor_global or 0 for c in Contrato.query.filter_by(orgao_id=orgao.id)
                    if c.data_assinatura and c.data_assinatura.year == ano)
        if total:
            concentracao.append({"orgao": orgao.razao_social, "ano": ano, "valor": valor, "total": total,
                                 "percentual": round(float(valor / total) * 100, 1)})
    return render_template("fornecedor.html", f=f, sancoes=sancoes, contratos=contratos, concentracao=concentracao)


def _somas(f):
    somas = defaultdict(int)
    for c in f.contratos:
        if c.data_assinatura and c.valor_global:
            somas[(c.orgao, c.data_assinatura.year)] += c.valor_global
    return somas
