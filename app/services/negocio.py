"""Métricas do modelo de negócio e dados de demonstração para a banca.

Os dados de demonstração só criam contas, assinaturas, seguidos, uso de API e pedidos com e-mail
@demo.fiscal-ai.local. Nunca criam contrato, alerta, fornecedor ou político: o dado público é sempre real.
"""
from __future__ import annotations

import random
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import (Assinatura, ChaveApi, Contrato, Fornecedor, PedidoInstitucional, Politico, Seguido, UsoApi,
                      Usuario)
from . import api_chaves, contas

DOMINIO_DEMO = "@demo.fiscal-ai.local"
EMAIL_BANCA = "banca" + DOMINIO_DEMO
NOMES_DEMO = ["Marina Costa", "Rafael Souza", "Juliana Lima", "Pedro Alves", "Camila Rocha", "Thiago Melo",
              "Larissa Pinto", "Redação Ilha Notícias"]
# plano, período, cancelada?  (4 mensais, 2 anuais, 1 cancelada, 1 institucional)
PLANOS_DEMO = [("pro", "mensal", False)] * 4 + [("pro", "anual", False)] * 2 + [("pro", "mensal", True),
                                                                                 ("institucional", "manual", False)]


def _vigentes(hoje: date) -> list[Assinatura]:
    return Assinatura.query.filter(Assinatura.fim >= hoje, Assinatura.status.in_(("ativa", "cancelada"))).all()


def resumo(hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    vig = _vigentes(hoje)
    pro = [a for a in vig if a.plano == "pro"]
    mrr = sum((a.valor if a.periodo == "mensal" else a.valor / 12 for a in pro if a.status == "ativa"), Decimal("0"))
    chamadas = db.session.query(func.coalesce(func.sum(UsoApi.chamadas), 0)).filter(
        UsoApi.dia > hoje - timedelta(days=30)).scalar()
    return {"contas": Usuario.query.count(), "pro_ativos": len({a.usuario_id for a in pro}),
            "institucionais_ativos": len({a.usuario_id for a in vig if a.plano == "institucional"}),
            "mrr": mrr.quantize(Decimal("0.01")), "cancelamentos": sum(1 for a in pro if a.status == "cancelada"),
            "seguidos": Seguido.query.count(), "chamadas_api_30d": int(chamadas),
            "pedidos_institucionais": PedidoInstitucional.query.count()}


def limpar_demo() -> int:
    usuarios = Usuario.query.filter(Usuario.email.like("%" + DOMINIO_DEMO)).all()
    for u in usuarios:
        db.session.delete(u)  # cascata: assinaturas, seguidos, chaves e uso da API
    PedidoInstitucional.query.filter(PedidoInstitucional.email.like("%" + DOMINIO_DEMO)).delete(
        synchronize_session=False)
    db.session.commit()
    return len(usuarios)


def _top_fornecedores(n: int) -> list[int]:
    linhas = (db.session.query(Contrato.fornecedor_id, func.count(Contrato.id).label("qtd"))
              .group_by(Contrato.fornecedor_id).order_by(func.count(Contrato.id).desc(), Contrato.fornecedor_id)
              .limit(n).all())
    return [fid for fid, _ in linhas]


def _usuario(nome: str, email: str, senha: str, criado_em: datetime) -> Usuario:
    u = Usuario(nome=nome, email=email, senha_hash=generate_password_hash(senha), criado_em=criado_em)
    db.session.add(u)
    return u


def criar_demo() -> str:
    """Cria (de novo) as contas fictícias e devolve a senha da conta da banca."""
    limpar_demo()
    sorte = random.Random(2026)
    agora, hoje = datetime.now(), date.today()
    fornecedores = _top_fornecedores(12)
    politicos = [p.id for p in Politico.query.order_by(Politico.id).limit(10)]

    for i, (nome, (plano, periodo, cancelada)) in enumerate(zip(NOMES_DEMO, PLANOS_DEMO), start=1):
        dias_atras = sorte.randint(5, 25 if periodo == "mensal" else 200)
        u = _usuario(nome, f"demo{i}{DOMINIO_DEMO}", secrets.token_urlsafe(12), agora - timedelta(days=dias_atras))
        inicio = hoje - timedelta(days=dias_atras)
        dur = 360 if plano == "institucional" else contas.DURACAO[periodo]
        valor = Decimal("0") if plano == "institucional" else contas.PRECOS[periodo]
        u.assinaturas.append(Assinatura(plano=plano, periodo=periodo, valor=valor, inicio=inicio,
                                        fim=inicio + timedelta(days=dur),
                                        status="cancelada" if cancelada else "ativa"))
        for fid in sorte.sample(fornecedores, min(len(fornecedores), sorte.randint(1, 4))):
            u.seguidos.append(Seguido(tipo="fornecedor", alvo_id=fid, criado_em=u.criado_em))
        for pid in sorte.sample(politicos, min(len(politicos), sorte.randint(0, 2))):
            u.seguidos.append(Seguido(tipo="politico", alvo_id=pid, criado_em=u.criado_em))
        if i % 2 == 0 or plano == "institucional":  # metade dos assinantes usa a API
            chave = ChaveApi(prefixo="fai_demo", chave_hash=api_chaves._hash(secrets.token_urlsafe(32)))
            u.chaves.append(chave)
            teto = 4000 if plano == "institucional" else 400
            for d in range(14):
                chave.usos.append(UsoApi(dia=hoje - timedelta(days=d), chamadas=sorte.randint(20, teto)))

    senha = secrets.token_urlsafe(9)
    banca = _usuario("Banca do TCC", EMAIL_BANCA, senha, agora - timedelta(days=90, minutes=1))
    banca.assinaturas.append(Assinatura(plano="pro", periodo="mensal", valor=contas.PRECOS["mensal"],
                                        status="ativa", inicio=hoje, fim=hoje + timedelta(days=30)))
    for fid in fornecedores[:3]:
        banca.seguidos.append(Seguido(tipo="fornecedor", alvo_id=fid, criado_em=agora - timedelta(days=90)))

    db.session.add_all([
        PedidoInstitucional(nome="Ana Ferreira", orgao="Câmara Municipal de Paço do Lumiar", municipio="Paço do Lumiar",
                            email="ana.ferreira" + DOMINIO_DEMO, mensagem="Queremos acompanhar os contratos do município."),
        PedidoInstitucional(nome="Carlos Nunes", orgao="Controladoria do Município de Imperatriz", municipio="Imperatriz",
                            email="carlos.nunes" + DOMINIO_DEMO, mensagem="Interesse em piloto para o controle interno."),
    ])
    db.session.commit()
    return senha


def criar_institucional(email: str, meses: int) -> Assinatura:
    u = Usuario.query.filter_by(email=contas.normalizar_email(email)).first()
    if u is None:
        raise LookupError(f"Nenhuma conta com o e-mail {email}. A pessoa precisa se cadastrar antes.")
    hoje = date.today()
    a = Assinatura(plano="institucional", periodo="manual", valor=Decimal("0"), status="ativa", inicio=hoje,
                   fim=hoje + timedelta(days=30 * meses))
    u.assinaturas.append(a)
    db.session.commit()
    return a
