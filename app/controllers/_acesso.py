"""Sessão do usuário, exigência de login/Pro e proteção CSRF (sem dependências novas)."""
from __future__ import annotations

import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from ..extensions import db
from ..models import Usuario
from ..services.contas import e_pro


def usuario_atual() -> Usuario | None:
    # cache por id da sessão: com o contexto da aplicação já aberto (testes), `g` sobrevive entre requisições
    uid = session.get("usuario_id")
    cache = g.get("_usuario_atual")
    if cache is None or cache[0] != uid:
        cache = (uid, db.session.get(Usuario, uid) if uid else None)
        g._usuario_atual = cache
    return cache[1]


def next_seguro(valor: str | None) -> str:
    """Só aceita caminho interno; qualquer coisa que possa sair do site vira a página da conta."""
    # caracteres de controle (tab, quebra de linha) são descartados pelos navegadores: "/\t/x.com" vira "//x.com"
    if (valor and valor.startswith("/") and not valor.startswith("//") and "\\" not in valor
            and not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in valor)):
        partes = urlsplit(valor)
        if not partes.scheme and not partes.netloc:
            return valor
    return url_for("contas.minha_conta")


def _caminho_atual() -> str:
    return request.full_path.rstrip("?") if request.query_string else request.path


def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        if usuario_atual() is None:
            return redirect(url_for("contas.entrar", next=_caminho_atual()))
        return view(*args, **kwargs)

    return envolvida


def pro_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        u = usuario_atual()
        if u is None:
            return redirect(url_for("contas.entrar", next=_caminho_atual()))
        if not e_pro(u):
            flash("Recurso do plano Pro.")
            return redirect(url_for("planos.pagina"))
        return view(*args, **kwargs)

    return envolvida


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def conferir_csrf():
    """before_request: todo POST fora da API exige o token da sessão."""
    if not current_app.config.get("CSRF_ATIVO", True) or request.method != "POST":
        return None
    if request.path.startswith("/api/"):
        return None
    enviado = request.form.get("csrf", "")
    esperado = session.get("csrf", "")
    if not esperado or not secrets.compare_digest(enviado, esperado):
        abort(400)
    return None
