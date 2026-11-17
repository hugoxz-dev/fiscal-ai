from flask import Blueprint, render_template
from sqlalchemy import func

from ..extensions import db
from ..models import Contrato, Convenio
from ..views._filtros import modalidade

bp = Blueprint("painel", __name__)


@bp.route("/")
def inicio():
    analisados = Contrato.query.filter(Contrato.analisado_em.isnot(None))
    total = analisados.count()
    kpis = {
        "contratos": total,
        "valor": db.session.query(func.sum(Contrato.valor_global)).filter(Contrato.analisado_em.isnot(None)).scalar(),
        "alto": analisados.filter(Contrato.nivel == "Alto").count(),
        "medio": analisados.filter(Contrato.nivel == "Médio").count(),
        "convenios": db.session.query(func.sum(Convenio.valor)).scalar(),
    }
    por_modalidade = (db.session.query(Contrato.modalidade_id, func.sum(Contrato.valor_global))
                      .filter(Contrato.analisado_em.isnot(None))
                      .group_by(Contrato.modalidade_id).order_by(func.sum(Contrato.valor_global).desc()).all())
    grafico = {"rotulos": [modalidade(m) for m, _ in por_modalidade],
               "valores": [float(v or 0) for _, v in por_modalidade]}
    top = analisados.order_by(Contrato.score.desc(), Contrato.valor_global.desc()).limit(10).all()
    return render_template("inicio.html", kpis=kpis, grafico=grafico, top=top)
