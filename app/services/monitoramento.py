"""Monitoramento do plano Pro: seguir fornecedores e políticos e ver o que mudou desde a última visita.

Contrato novo = `coletado_em` depois da referência; alerta novo = `criado_em` depois da referência (a análise
preserva a data de alertas que já existiam). Para político, contam só fornecedores com ligação CONFIRMADA.
"""
from __future__ import annotations

from datetime import datetime

from ..extensions import db
from ..models import Alerta, Contrato, Fornecedor, Politico, Seguido, Usuario
from .ligacoes import ligacoes_do_politico

MODELOS = {"fornecedor": Fornecedor, "politico": Politico}


def _alvo(tipo: str, alvo_id: int):
    if tipo not in MODELOS:
        raise ValueError(f"tipo inválido: {tipo}")
    alvo = db.session.get(MODELOS[tipo], alvo_id)
    if alvo is None:
        raise LookupError(f"{tipo} {alvo_id} não existe")
    return alvo


def _buscar(u: Usuario, tipo: str, alvo_id: int) -> Seguido | None:
    return Seguido.query.filter_by(usuario_id=u.id, tipo=tipo, alvo_id=alvo_id).first()


def seguir(u: Usuario, tipo: str, alvo_id: int) -> Seguido:
    _alvo(tipo, alvo_id)
    s = _buscar(u, tipo, alvo_id)
    if s is None:
        s = Seguido(usuario_id=u.id, tipo=tipo, alvo_id=alvo_id)
        db.session.add(s)
        db.session.commit()
    return s


def deixar(u: Usuario, tipo: str, alvo_id: int) -> None:
    s = _buscar(u, tipo, alvo_id)
    if s is not None:
        db.session.delete(s)
        db.session.commit()


def segue(u: Usuario | None, tipo: str, alvo_id: int) -> bool:
    return u is not None and _buscar(u, tipo, alvo_id) is not None


def _referencia(u: Usuario, s: Seguido) -> datetime:
    visita = u.ultima_visita_monitoramento
    return max(visita, s.criado_em) if visita else s.criado_em


def novidades(u: Usuario) -> list[dict]:
    itens = []
    for s in sorted(u.seguidos, key=lambda s: s.criado_em, reverse=True):
        alvo = db.session.get(MODELOS.get(s.tipo, Fornecedor), s.alvo_id)
        if alvo is None:
            continue
        ref = _referencia(u, s)
        if s.tipo == "fornecedor":
            ids = [alvo.id]
        else:
            ids = sorted({l.fornecedor.id for l in ligacoes_do_politico(alvo) if l.confirmada})
        contratos = (Contrato.query.filter(Contrato.fornecedor_id.in_(ids), Contrato.coletado_em > ref)
                     .order_by(Contrato.coletado_em.desc()).all()) if ids else []
        alertas = []
        if s.tipo == "fornecedor":
            alertas = (Alerta.query.join(Contrato).filter(Contrato.fornecedor_id == alvo.id, Alerta.criado_em > ref)
                       .order_by(Alerta.criado_em.desc()).all())
        itens.append({"seguido": s, "alvo": alvo, "contratos": contratos, "alertas": alertas})
    return itens


def contar(u: Usuario) -> int:
    return sum(len(i["contratos"]) + len(i["alertas"]) for i in novidades(u))


def marcar_visita(u: Usuario) -> None:
    u.ultima_visita_monitoramento = datetime.now()
    db.session.commit()
