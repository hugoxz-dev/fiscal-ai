"""Ligações entre políticos e fornecedores da prefeitura.

Uma ligação indica relação registrada em dados públicos, não irregularidade. Confirmada = nome e
dígitos do CPF conferem; não confirmada = só o nome coincide. Nenhum campo expõe CPF.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ..extensions import db
from ..models import Contrato, DespesaParlamentar, Doacao, Fornecedor, Politico, Socio
from ..views._filtros import moeda
from .texto import cpf_meio, cpf_valido, normalizar

_ORDEM_NIVEL = {"Baixo": 1, "Médio": 2, "Alto": 3}


@dataclass
class Ligacao:
    tipo: str  # socio_doou | politico_socio | fornecedor_pf | cota
    confirmada: bool
    politico: Politico
    fornecedor: Fornecedor
    pessoa: str
    valor: Decimal | None
    descricao: str


def resumo_fornecedor(f: Fornecedor) -> dict:
    contratos = Contrato.query.filter_by(fornecedor_id=f.id).all()
    nivel = None
    for c in contratos:
        if _ORDEM_NIVEL.get(c.nivel, 0) > _ORDEM_NIVEL.get(nivel, 0):
            nivel = c.nivel
    total = sum((c.valor_global or Decimal("0") for c in contratos), Decimal("0"))
    return {"contratos": len(contratos), "total": total, "nivel": nivel}


def _calcular(politico: Politico | None = None, fornecedor: Fornecedor | None = None) -> list[Ligacao]:
    politicos = [politico] if politico else Politico.query.all()
    por_id = {p.id: p for p in politicos}
    if not por_id:
        return []

    q_socio = Socio.query
    q_forn = Fornecedor.query.filter_by(tipo="PF")
    q_desp = DespesaParlamentar.query.filter(
        DespesaParlamentar.documento.in_(db.session.query(Fornecedor.documento)))
    if fornecedor:
        q_socio = q_socio.filter_by(fornecedor_id=fornecedor.id)
        q_forn = q_forn.filter_by(id=fornecedor.id)
        q_desp = q_desp.filter_by(documento=fornecedor.documento)
    if politico:
        q_desp = q_desp.filter_by(politico_id=politico.id)
    q_doa = Doacao.query
    if politico:
        q_doa = q_doa.filter_by(politico_id=politico.id)

    socios = q_socio.all()
    por_chave: dict[tuple, list[Socio]] = defaultdict(list)
    por_nome: dict[str, list[Socio]] = defaultdict(list)
    for s in socios:
        por_nome[s.nome_norm].append(s)
        if s.cpf_meio:
            por_chave[(s.nome_norm, s.cpf_meio)].append(s)

    saida: dict[tuple, Ligacao] = {}

    def _add(lig: Ligacao, soma: bool = False) -> None:
        chave = (lig.tipo, lig.politico.id, lig.fornecedor.id, lig.pessoa)
        if chave in saida:
            if soma and lig.valor is not None:
                saida[chave].valor = (saida[chave].valor or Decimal("0")) + lig.valor
            return
        saida[chave] = lig

    doacoes = [d for d in q_doa.all() if d.politico_id in por_id]

    # socio_doou: soma por (político, fornecedor, sócio); originárias e diretas carregam o CPF do doador
    for d in doacoes:
        if not cpf_valido(d.documento):
            continue
        for s in por_chave.get((d.nome_norm, cpf_meio(d.documento)), []):
            _add(Ligacao("socio_doou", True, por_id[d.politico_id], s.fornecedor, s.nome,
                         d.valor or Decimal("0"), ""), soma=True)

    # politico_socio
    for p in politicos:
        nome = normalizar(p.nome)
        if p.cpf:
            for s in por_chave.get((nome, cpf_meio(p.cpf)), []):
                _add(Ligacao("politico_socio", True, p, s.fornecedor, s.nome, None, ""))
            # sócio sem CPF informado (BrasilAPI omitiu): só o nome coincide
            alvo = [s for s in por_nome.get(nome, []) if not s.cpf_meio]
        else:
            alvo = por_nome.get(nome, [])
        for s in alvo:
            _add(Ligacao("politico_socio", False, p, s.fornecedor, s.nome, None, ""))

    # fornecedor_pf: caminhos confirmados primeiro (doador; é o próprio político), depois só por nome
    pf = q_forn.all()
    pf_por_doc = {f.documento: f for f in pf}
    for d in doacoes:
        doc = cpf_valido(d.documento)
        if doc and doc in pf_por_doc:
            f = pf_por_doc[doc]
            p = por_id[d.politico_id]
            _add(Ligacao("fornecedor_pf", True, p, f, f.nome, d.valor or Decimal("0"), ""), soma=True)
    for p in politicos:
        if p.cpf and p.cpf in pf_por_doc:
            f = pf_por_doc[p.cpf]
            chave = ("fornecedor_pf", p.id, f.id, f.nome)
            if chave in saida:
                saida[chave].descricao = _descrever_pf_proprio(p, f)
            else:
                _add(Ligacao("fornecedor_pf", True, p, f, f.nome, None, _descrever_pf_proprio(p, f)))
    for p in politicos:
        if not p.cpf:
            for f in pf:
                if normalizar(f.nome) == normalizar(p.nome):
                    _add(Ligacao("fornecedor_pf", False, p, f, f.nome, None, ""))

    # cota parlamentar
    despesas = q_desp.all()
    docs = {d.documento for d in despesas if d.documento}
    forns = {f.documento: f for f in Fornecedor.query.filter(Fornecedor.documento.in_(docs)).all()} if docs else {}
    for d in despesas:
        f = forns.get(d.documento)
        if f and d.politico_id in por_id:
            _add(Ligacao("cota", True, por_id[d.politico_id], f, f.nome, d.valor or Decimal("0"), ""), soma=True)

    ligs = list(saida.values())
    for l in ligs:
        if not l.descricao:
            l.descricao = _descrever(l)
    return ligs


def _descrever_pf_proprio(p: Politico, f: Fornecedor) -> str:
    return f"{f.nome}, fornecedor pessoa física, é {p.nome}"


def _descrever(l: Ligacao) -> str:
    forn = l.fornecedor.nome
    pol = l.politico.nome
    v = moeda(l.valor) if l.valor is not None else None
    if l.tipo == "socio_doou":
        return f"{l.pessoa}, sócio de {forn}, doou {v} a {pol}"
    if l.tipo == "politico_socio":
        return f"{pol} consta como sócio de {forn}"
    if l.tipo == "fornecedor_pf":
        if l.confirmada:  # doação do fornecedor PF (o caso "é o político" já nasce com descrição)
            return f"{forn}, fornecedor pessoa física, doou {v} a {pol}"
        return f"{forn}, fornecedor pessoa física, tem o mesmo nome de {pol}"
    return f"{pol} pagou {v} de cota parlamentar a {forn}"


def _ordenar(ligs: list[Ligacao]) -> list[Ligacao]:
    return sorted(ligs, key=lambda l: (not l.confirmada, -(l.valor or Decimal("0"))))


def ligacoes_do_politico(p: Politico) -> list[Ligacao]:
    return _ordenar(_calcular(politico=p))


def ligacoes_do_fornecedor(f: Fornecedor) -> list[Ligacao]:
    return _ordenar(_calcular(fornecedor=f))


def contar_ligacoes() -> dict[int, int]:
    cont: dict[int, int] = defaultdict(int)
    for l in _calcular():
        if l.confirmada:
            cont[l.politico.id] += 1
    return dict(cont)
