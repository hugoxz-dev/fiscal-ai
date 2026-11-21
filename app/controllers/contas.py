from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..services import api_chaves
from ..services import contas as svc
from ._acesso import login_obrigatorio, next_seguro, pro_obrigatorio, usuario_atual

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
    chave = api_chaves.ativa(u)
    return render_template("conta.html", u=u, assinatura=svc.assinatura_ativa(u), chave=chave,
                           chamadas_hoje=api_chaves.chamadas_hoje(chave) if chave else 0,
                           chave_nova=session.pop("chave_nova", None))


@bp.route("/conta/chave", methods=["POST"])
@pro_obrigatorio
def gerar_chave():
    # a chave completa vai só uma vez para a sessão e é exibida (e descartada) na próxima página
    session["chave_nova"] = api_chaves.gerar(usuario_atual())
    flash("Chave de API gerada. Copie agora: ela não será mostrada de novo.")
    return redirect(url_for("contas.minha_conta"))


@bp.route("/conta/chave/revogar", methods=["POST"])
@pro_obrigatorio
def revogar_chave():
    api_chaves.revogar(usuario_atual())
    flash("Chave de API revogada.")
    return redirect(url_for("contas.minha_conta"))
