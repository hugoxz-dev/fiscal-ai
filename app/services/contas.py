"""Contas de usuário e assinaturas (cobrança em modo demonstração: nada é cobrado nem guardado de cartão)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import Assinatura, Usuario

PRECOS = {"mensal": Decimal("19.90"), "anual": Decimal("199.00")}
DURACAO = {"mensal": 30, "anual": 365}
SENHA_MINIMA = 8


def normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()


def criar_usuario(nome: str, email: str, senha: str) -> Usuario:
    nome, email = (nome or "").strip(), normalizar_email(email)
    if not nome:
        raise ValueError("Informe seu nome.")
    if "@" not in email or len(email) > 190:
        raise ValueError("Informe um e-mail válido.")
    if len(senha or "") < SENHA_MINIMA:
        raise ValueError(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if Usuario.query.filter_by(email=email).first():
        raise ValueError("Este e-mail já está cadastrado.")
    u = Usuario(nome=nome[:120], email=email, senha_hash=generate_password_hash(senha))
    db.session.add(u)
    db.session.commit()
    return u


def autenticar(email: str, senha: str) -> Usuario | None:
    u = Usuario.query.filter_by(email=normalizar_email(email)).first()
    return u if u and check_password_hash(u.senha_hash, senha or "") else None


def assinatura_ativa(u: Usuario | None, hoje: date | None = None) -> Assinatura | None:
    """Assinatura vigente: ativa ou cancelada que ainda não chegou ao fim (cancelar mantém o acesso até o fim)."""
    if u is None:
        return None
    hoje = hoje or date.today()
    vigentes = [a for a in u.assinaturas if a.status in ("ativa", "cancelada") and a.fim >= hoje]
    return max(vigentes, key=lambda a: a.fim, default=None)


def e_pro(u: Usuario | None, hoje: date | None = None) -> bool:
    return assinatura_ativa(u, hoje) is not None


def assinar(u: Usuario, periodo: str, hoje: date | None = None) -> Assinatura:
    """Checkout de demonstração. Se já há assinatura vigente, estende o fim em vez de criar outra."""
    if periodo not in PRECOS:
        raise ValueError(f"Período inválido: {periodo}")
    hoje = hoje or date.today()
    dias = timedelta(days=DURACAO[periodo])
    a = assinatura_ativa(u, hoje)
    if a is not None and a.plano != "pro":
        raise ValueError("Conta institucional: o plano é gerido pelo administrador.")
    if a is None:
        a = Assinatura(plano="pro", inicio=hoje, fim=hoje + dias)
        u.assinaturas.append(a)
    else:
        a.fim = a.fim + dias
    a.periodo, a.valor, a.status = periodo, PRECOS[periodo], "ativa"
    db.session.commit()
    return a


def cancelar(u: Usuario) -> None:
    """Cancela a renovação; o acesso continua até o fim já pago."""
    a = assinatura_ativa(u)
    if a is not None:
        a.status = "cancelada"
        db.session.commit()
