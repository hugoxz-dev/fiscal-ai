from flask import Blueprint, render_template

from ..services.analisador import REGRAS
from ..services.regras.config import LIMITES_DISPENSA, NIVEIS, PESOS

bp = Blueprint("metodologia", __name__)


@bp.route("/metodologia")
def pagina():
    regras = [{"nome": r.nome, "base_legal": r.base_legal, "descricao": r.descricao, "peso": PESOS[r.codigo]}
              for r in REGRAS]
    return render_template("metodologia.html", regras=regras, niveis=NIVEIS, limites=LIMITES_DISPENSA)
