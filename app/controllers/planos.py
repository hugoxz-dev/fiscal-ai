from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import PedidoInstitucional
from ..services import contas as svc
from ._acesso import login_obrigatorio, usuario_atual

bp = Blueprint("planos", __name__)

CAMPOS_CARTAO = ("numero", "nome", "validade", "cvv")
CAMPOS_PEDIDO = ("nome", "orgao", "municipio", "email")


@bp.route("/planos")
def pagina():
    return render_template("planos.html", precos=svc.PRECOS, pedido={}, erro_pedido=None)


@bp.route("/planos/checkout", methods=["GET", "POST"])
@login_obrigatorio
def checkout():
    periodo = request.args.get("periodo", "mensal")
    if periodo not in svc.PRECOS:
        abort(404)
    atual = svc.assinatura_ativa(usuario_atual())
    if atual is not None and atual.plano != "pro":
        flash("Sua conta é Institucional: o plano é gerido pelo administrador.")
        return redirect(url_for("contas.minha_conta"))
    erro = None
    if request.method == "POST":
        # modo demonstração: os campos do cartão só precisam estar preenchidos e são descartados aqui
        if all((request.form.get(c) or "").strip() for c in CAMPOS_CARTAO):
            svc.assinar(usuario_atual(), periodo)
            flash("Assinatura Pro ativada (modo demonstração — nenhuma cobrança foi feita).")
            return redirect(url_for("contas.minha_conta"))
        erro = "Preencha todos os campos do cartão de teste."
    return render_template("checkout.html", periodo=periodo, valor=svc.PRECOS[periodo],
                           dias=svc.DURACAO[periodo], erro=erro)


@bp.route("/conta/cancelar", methods=["POST"])
@login_obrigatorio
def cancelar():
    svc.cancelar(usuario_atual())
    flash("Assinatura cancelada. O acesso Pro continua até o fim do período.")
    return redirect(url_for("contas.minha_conta"))


@bp.route("/planos/institucional", methods=["POST"])
def institucional():
    dados = {c: (request.form.get(c) or "").strip() for c in (*CAMPOS_PEDIDO, "mensagem")}
    if not all(dados[c] for c in CAMPOS_PEDIDO) or "@" not in dados["email"]:
        return render_template("planos.html", precos=svc.PRECOS, pedido=dados,
                               erro_pedido="Preencha nome, órgão, município e um e-mail válido.")
    db.session.add(PedidoInstitucional(nome=dados["nome"][:120], orgao=dados["orgao"][:190],
                                       municipio=dados["municipio"][:120], email=dados["email"][:190],
                                       mensagem=dados["mensagem"][:2000] or None))
    db.session.commit()
    return render_template("institucional_obrigado.html", nome=dados["nome"])
