from decimal import Decimal

from app.extensions import db
from app.models import DespesaParlamentar, Doacao, Fornecedor, Politico, Socio
from app.services.ligacoes import (contar_ligacoes, ligacoes_do_fornecedor, ligacoes_do_politico,
                                   resumo_fornecedor)
from app.services.texto import cpf_meio, normalizar

CPF_A = "11122233344"
CPF_B = "99988877766"


def _forn(doc="12345678000199", nome="CONSTRUTORA ABC LTDA", tipo="PJ"):
    f = Fornecedor(documento=doc, nome=nome, tipo=tipo)
    db.session.add(f)
    db.session.commit()
    return f


def _socio(f, nome, cpf=None):
    s = Socio(fornecedor=f, nome=nome, nome_norm=normalizar(nome), cpf_meio=cpf_meio(cpf))
    db.session.add(s)
    db.session.commit()
    return s


def _pol(nome="Beltrano da Silva", cpf=None, cargo="Vereador"):
    p = Politico(nome=nome, cpf=cpf, cargo=cargo, uf="MA")
    db.session.add(p)
    db.session.commit()
    return p


def _doacao(p, nome, doc, valor, sq="1", originario=False):
    d = Doacao(politico=p, sq_receita=sq, documento=doc, nome=nome, nome_norm=normalizar(nome),
               valor=Decimal(valor), originario=originario)
    db.session.add(d)
    db.session.commit()
    return d


def test_socio_doou_confirma_por_nome_e_cpf(app):
    f = _forn()
    _socio(f, "Fulano de Tal", CPF_A)
    p = _pol()
    _doacao(p, "FULANO DE TAL", CPF_A, "6000.00", sq="1")
    _doacao(p, "FULANO DE TAL", CPF_A, "4000.00", sq="2")
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1
    assert ligs[0].tipo == "socio_doou" and ligs[0].confirmada
    assert ligs[0].valor == Decimal("10000.00")
    assert ligs[0].fornecedor.id == f.id
    assert contar_ligacoes() == {p.id: 1}


def test_homonimo_com_cpf_diferente_nao_liga(app):
    f = _forn()
    _socio(f, "Fulano de Tal", CPF_A)
    p = _pol()
    _doacao(p, "Fulano de Tal", CPF_B, "100.00")
    assert ligacoes_do_politico(p) == []


def test_socio_pj_nao_liga(app):
    f = _forn()
    _socio(f, "Fulano de Tal", None)
    p = _pol()
    _doacao(p, "Fulano de Tal", CPF_A, "100.00")
    assert ligacoes_do_politico(p) == []


def test_politico_socio_sem_cpf_vira_nao_confirmada(app):
    f = _forn()
    _socio(f, "Beltrano da Silva", CPF_A)
    p = _pol(cpf=None)
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1
    assert ligs[0].tipo == "politico_socio" and ligs[0].confirmada is False
    assert contar_ligacoes() == {}


def test_politico_socio_com_cpf_confirma(app):
    f = _forn()
    _socio(f, "Beltrano da Silva", CPF_A)
    p = _pol(cpf=CPF_A)
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1 and ligs[0].confirmada
    outro = _pol("Beltrano da Silva", CPF_B, "Senador")
    assert ligacoes_do_politico(outro) == []


def test_fornecedor_pf_e_o_politico(app):
    f = _forn(doc=CPF_A, nome="BELTRANO DA SILVA", tipo="PF")
    p = _pol(cpf=CPF_A, cargo="Deputado Federal")
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1
    assert ligs[0].tipo == "fornecedor_pf" and ligs[0].confirmada
    assert ligs[0].fornecedor.id == f.id


def test_fornecedor_pf_doador_do_politico(app):
    f = _forn(doc=CPF_B, nome="CICLANO", tipo="PF")
    p = _pol()
    _doacao(p, "Ciclano", CPF_B, "50.00")
    ligs = ligacoes_do_fornecedor(f)
    assert [l.tipo for l in ligs] == ["fornecedor_pf"] and ligs[0].confirmada
    assert ligs[0].valor == Decimal("50.00")
    assert ligs[0].descricao == "CICLANO, fornecedor pessoa física, doou R$ 50,00 a Beltrano da Silva"


def test_pf_confirmada_por_doacao_nao_e_bloqueada_por_nome(app):
    f = _forn(doc=CPF_B, nome="Beltrano da Silva", tipo="PF")
    p = _pol(cpf=None)
    assert [l.confirmada for l in ligacoes_do_politico(p)] == [False]
    _doacao(p, "Beltrano da Silva", CPF_B, "70.00")
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1 and ligs[0].confirmada and "doou R$ 70,00" in ligs[0].descricao
    assert contar_ligacoes() == {p.id: 1}


def test_cota_soma_por_fornecedor(app):
    f = _forn()
    p = _pol(cargo="Deputado Federal")
    for i, v in enumerate(["100.00", "250.50"]):
        db.session.add(DespesaParlamentar(politico=p, documento=f.documento, valor=Decimal(v),
                                          cod_documento=str(i)))
    db.session.commit()
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 1 and ligs[0].tipo == "cota" and ligs[0].confirmada
    assert ligs[0].valor == Decimal("350.50")


def test_ligacoes_do_fornecedor_e_resumo(app, fazer_contrato):
    f = _forn()
    fazer_contrato(fornecedor=f, nivel="Médio", valor_global=Decimal("100.00"))
    fazer_contrato(fornecedor=f, nivel="Baixo", valor_global=Decimal("50.00"))
    _socio(f, "Fulano de Tal", CPF_A)
    p = _pol()
    _doacao(p, "Fulano de Tal", CPF_A, "10000")
    r = resumo_fornecedor(f)
    assert r == {"contratos": 2, "total": Decimal("150.00"), "nivel": "Médio"}
    ligs = ligacoes_do_fornecedor(f)
    assert len(ligs) == 1 and ligs[0].politico.id == p.id
    assert "R$ 10.000,00" in ligs[0].descricao


def test_descricao_sem_cpf(app):
    f = _forn(doc=CPF_A, nome="BELTRANO DA SILVA", tipo="PF")
    g = _forn()
    _socio(g, "Fulano de Tal", CPF_B)
    p = _pol(cpf=CPF_A)
    _doacao(p, "Fulano de Tal", CPF_B, "10.00")
    db.session.add(DespesaParlamentar(politico=p, documento=g.documento, valor=Decimal("1"), cod_documento="x"))
    db.session.commit()
    ligs = ligacoes_do_politico(p)
    assert len(ligs) == 3
    for l in ligs:
        for cpf in (CPF_A, CPF_B, cpf_meio(CPF_A), cpf_meio(CPF_B)):
            assert cpf not in l.descricao and cpf not in l.pessoa
