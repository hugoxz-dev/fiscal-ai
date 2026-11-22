from flask import Blueprint, render_template

from ..services.analisador import REGRAS, REGRAS_DESATIVADAS
from ..services.regras.config import LIMITES_DISPENSA, NIVEIS, PESOS

bp = Blueprint("metodologia", __name__)


@bp.route("/metodologia")
def pagina():
    regras = [{"nome": r.nome, "base_legal": r.base_legal, "descricao": r.descricao, "peso": PESOS[r.codigo]}
              for r in REGRAS]
    desativadas = [{"nome": r.nome, "base_legal": r.base_legal, "motivo": motivo}
                   for r, motivo in REGRAS_DESATIVADAS.items()]
    return render_template("metodologia.html", regras=regras, desativadas=desativadas, niveis=NIVEIS,
                           limites=LIMITES_DISPENSA)
