from flask import Blueprint, redirect, render_template, request, session, url_for

from ..services import contas as svc
from ._acesso import login_obrigatorio, next_seguro, usuario_atual

bp = Blueprint("contas", __name__)


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    if request.method == "POST":
        u = svc.autenticar(request.form.get("email"), request.form.get("senha"))
        if u:
            session.clear()
            session["usuario_id"] = u.id
            return redirect(next_seguro(request.args.get("next")))
        erro = "E-mail ou senha inválidos."
    return render_template("conta_entrar.html", erro=erro, email=request.form.get("email", ""),
                           proximo=request.args.get("next", ""))


@bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    erro = None
    if request.method == "POST":
        try:
            u = svc.criar_usuario(request.form.get("nome"), request.form.get("email"), request.form.get("senha"))
        except ValueError as e:
            erro = str(e)
        else:
            session.clear()
            session["usuario_id"] = u.id
            return redirect(next_seguro(request.args.get("next")))
    return render_template("conta_cadastro.html", erro=erro, form=request.form, proximo=request.args.get("next", ""))


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("painel.inicio"))


@bp.route("/conta")
@login_obrigatorio
def minha_conta():
    u = usuario_atual()
    return render_template("conta.html", u=u, assinatura=svc.assinatura_ativa(u))
