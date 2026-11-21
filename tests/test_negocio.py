from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (Alerta, Assinatura, Contrato, Fornecedor, PedidoInstitucional, Politico, Seguido, UsoApi,
                        Usuario)
from app.services import contas, negocio


def _contagens():
    return [m.query.count() for m in (Contrato, Alerta, Fornecedor, Politico)]


@pytest.fixture
def base_publica(app, fazer_contrato):
    for i in range(4):
        fazer_contrato(fornecedor=Fornecedor(documento=f"1000000000{i:04d}", nome=f"FORN {i}", tipo="PJ"))
    fazer_contrato()
    fazer_contrato()  # o fornecedor padrão fica com mais contratos que os outros
    db.session.add(Politico(nome="Fulano", cargo="Vereador", uf="MA"))
    db.session.commit()


def test_demo_nao_cria_dado_publico(app, base_publica):
    antes = _contagens()
    negocio.criar_demo()
    assert _contagens() == antes


def test_demo_idempotente_e_limpar(app, base_publica, fazer_usuario):
    real = fazer_usuario(email="real@x.com")
    negocio.criar_demo()
    senha = negocio.criar_demo()  # a segunda rodada recria a conta da banca com senha nova
    demo = Usuario.query.filter(Usuario.email.like("%@demo.fiscal-ai.local")).all()
    assert len(demo) == 9 and PedidoInstitucional.query.count() == 2
    banca = Usuario.query.filter_by(email="banca@demo.fiscal-ai.local").one()
    assert contas.autenticar("banca@demo.fiscal-ai.local", senha) is not None and contas.e_pro(banca)
    assert len(banca.seguidos) == 3 and all(s.criado_em < datetime.now() - timedelta(days=89) for s in banca.seguidos)
    assert UsoApi.query.count() > 0
    assert negocio.limpar_demo() == 9
    assert Usuario.query.all() == [real] and PedidoInstitucional.query.count() == 0
    assert Seguido.query.count() == 0 and Assinatura.query.count() == 0 and UsoApi.query.count() == 0


def test_demo_segue_os_fornecedores_com_mais_contratos(app, base_publica):
    negocio.criar_demo()
    banca = Usuario.query.filter_by(email="banca@demo.fiscal-ai.local").one()
    padrao = Fornecedor.query.filter_by(documento="12345678000199").one()
    assert padrao.id in {s.alvo_id for s in banca.seguidos if s.tipo == "fornecedor"}


def test_demo_em_banco_vazio_nao_quebra(app):
    negocio.criar_demo()
    assert Usuario.query.count() == 9


def test_resumo_mrr(app, fazer_usuario):
    contas.assinar(fazer_usuario(email="a@x.com"), "mensal")
    contas.assinar(fazer_usuario(email="b@x.com"), "anual")
    c = fazer_usuario(email="c@x.com")
    contas.assinar(c, "mensal")
    contas.cancelar(c)
    r = negocio.resumo()
    assert r["contas"] == 3 and r["pro_ativos"] == 3 and r["cancelamentos"] == 1
    assert r["mrr"] == Decimal("36.48")  # 19,90 + 199/12; o cancelado não renova


def test_institucional(app, fazer_usuario):
    u = fazer_usuario()
    a = negocio.criar_institucional("ANA@x.com", 12)
    assert a.plano == "institucional" and a.valor == Decimal("0") and a.fim == date.today() + timedelta(days=360)
    assert negocio.resumo()["institucionais_ativos"] == 1 and contas.e_pro(u)
    with pytest.raises(LookupError):
        negocio.criar_institucional("ninguem@x.com", 1)


def test_cli_leads_e_resumo(app):
    db.session.add(PedidoInstitucional(nome="Bia", orgao="Câmara de Paço", municipio="Paço", email="b@x.com"))
    db.session.commit()
    runner = app.test_cli_runner()
    assert "Câmara de Paço" in runner.invoke(args=["leads"]).output
    saida = runner.invoke(args=["negocio", "resumo"]).output
    assert "Receita mensal" in saida and "R$ 0,00" in saida


def test_cli_demo_e_institucional(app, fazer_usuario):
    runner = app.test_cli_runner()
    saida = runner.invoke(args=["negocio", "demo"]).output
    assert "banca@demo.fiscal-ai.local" in saida
    assert "removidas" in runner.invoke(args=["negocio", "demo", "--limpar"]).output
    fazer_usuario()
    assert "Institucional" in runner.invoke(args=["negocio", "institucional", "--email", "ana@x.com",
                                                  "--meses", "6"]).output
