from datetime import date

from flask import Blueprint, abort, render_template, request
from sqlalchemy import and_, or_

from ..extensions import db
from ..models import Contrato, Fornecedor, Orgao
from ..services.analisador import REGRAS
from ..views._filtros import MODALIDADES

bp = Blueprint("contratos", __name__)
POR_PAGINA = 25
ORDENS = {"score": Contrato.score, "valor": Contrato.valor_global, "data": Contrato.data_assinatura}
NIVEIS = ("Alto", "Médio", "Baixo")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _data(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def filtrar_contratos(a):
    """Filtros da lista de contratos (mesma regra para a página, o CSV e a API). Devolve (consulta, filtros)."""
    f = {"orgao": _int(a.get("orgao")), "modalidade": _int(a.get("modalidade")),
         "nivel": a.get("nivel") if a.get("nivel") in NIVEIS else None,
         "de": _data(a.get("de")), "ate": _data(a.get("ate")),
         "fornecedor": (a.get("fornecedor") or "").strip()[:100],
         "ordem": a.get("ordem") if a.get("ordem") in ORDENS else "score"}
    q = Contrato.query.join(Fornecedor)
    if f["orgao"]:
        q = q.filter(Contrato.orgao_id == f["orgao"])
    if f["modalidade"]:
        q = q.filter(Contrato.modalidade_id == f["modalidade"])
    if f["nivel"]:
        q = q.filter(Contrato.nivel == f["nivel"])
    if f["de"]:
        q = q.filter(Contrato.data_assinatura >= f["de"])
    if f["ate"]:
        q = q.filter(Contrato.data_assinatura <= f["ate"])
    if f["fornecedor"]:
        digitos = "".join(c for c in f["fornecedor"] if c.isdigit())
        condicoes = [Fornecedor.nome.ilike(f"%{f['fornecedor']}%")]
        if len(digitos) >= 3:
            # só CNPJ: busca por dígitos de CPF permitiria confirmar o CPF de uma pessoa física
            condicoes.append(and_(Fornecedor.tipo == "PJ", Fornecedor.documento.like(f"%{digitos}%")))
        q = q.filter(or_(*condicoes))
    return q.order_by(ORDENS[f["ordem"]].desc(), Contrato.id.desc()), f


@bp.route("/contratos")
def lista():
    q, f = filtrar_contratos(request.args)
    pagina = max(_int(request.args.get("pagina")) or 1, 1)
    paginacao = q.paginate(page=pagina, per_page=POR_PAGINA, error_out=False)
    return render_template("contratos.html", paginacao=paginacao, filtros=f, orgaos=Orgao.query.all(),
                           modalidades=MODALIDADES, niveis=NIVEIS)


def contexto_detalhe(id: int) -> dict:
    contrato = db.session.get(Contrato, id) or abort(404)
    nomes = {r.codigo: r for r in REGRAS}
    alertas = sorted(contrato.alertas, key=lambda al: -al.pontos)
    pdfs = sorted({e.publicacao.url_pdf: e.publicacao for e in contrato.extratos}.values(),
                  key=lambda p: p.data_edicao or date.min)
    return {"c": contrato, "alertas": alertas, "regras": nomes, "pdfs": pdfs}


@bp.route("/contratos/<int:id>")
def detalhe(id):
    return render_template("contrato_detalhe.html", **contexto_detalhe(id))
