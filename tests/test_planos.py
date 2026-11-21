from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import inspect

from app.extensions import db
from app.models import Assinatura, PedidoInstitucional
from app.services import contas

CARTAO = {"numero": "4111111111111111", "nome": "ANA TESTE", "validade": "12/30", "cvv": "123"}


def test_planos_publico_mostra_tres_planos_e_precos(client):
    html = client.get("/planos").get_data(as_text=True).replace("Sob consulta", "sob consulta")
    for trecho in ("Cidadão", "Pro", "Institucional", "19,90", "199", "sob consulta", "R$ 490"):
        assert trecho in html, trecho


def test_checkout_exige_login(client):
    r = client.get("/planos/checkout?periodo=mensal")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_checkout_mostra_aviso_demo(client, fazer_usuario, logar):
    logar(client, fazer_usuario())
    html = client.get("/planos/checkout?periodo=anual").get_data(as_text=True)
    assert "Modo demonstração — nenhuma cobrança é feita." in html and "199,00" in html


def test_checkout_periodo_invalido_404(client, fazer_usuario, logar):
    logar(client, fazer_usuario())
    assert client.get("/planos/checkout?periodo=vitalicio").status_code == 404


def test_checkout_ativa_pro_sem_guardar_cartao(client, fazer_usuario, logar):
    u = fazer_usuario()
    logar(client, u)
    r = client.post("/planos/checkout?periodo=anual", data=CARTAO)
    assert r.status_code == 302 and r.headers["Location"].endswith("/conta")
    a = contas.assinatura_ativa(u)
    assert a.plano == "pro" and a.valor == Decimal("199.00") and a.fim == date.today() + timedelta(days=365)
    # nenhuma coluna de nenhuma tabela guarda o cartão
    for tabela in db.metadata.sorted_tables:
        for linha in db.session.execute(tabela.select()).all():
            assert not any("1111" in str(v) or "4111" in str(v) for v in linha), tabela.name


def test_checkout_cartao_incompleto(client, fazer_usuario, logar):
    u = fazer_usuario()
    logar(client, u)
    r = client.post("/planos/checkout?periodo=mensal", data={**CARTAO, "cvv": ""})
    assert r.status_code == 200 and not contas.e_pro(u)


def test_assinar_de_novo_estende(app, fazer_usuario):
    u = fazer_usuario()
    contas.assinar(u, "mensal")
    contas.assinar(u, "mensal")
    assert Assinatura.query.count() == 1
    assert contas.assinatura_ativa(u).fim == date.today() + timedelta(days=60)


def test_assinar_periodo_invalido(app, fazer_usuario):
    import pytest

    with pytest.raises(ValueError):
        contas.assinar(fazer_usuario(), "semanal")


def test_cancelar_mantem_ate_fim(app, fazer_usuario):
    u = fazer_usuario()
    a = contas.assinar(u, "mensal")
    contas.cancelar(u)
    assert a.status == "cancelada" and contas.e_pro(u)
    assert not contas.e_pro(u, hoje=a.fim + timedelta(days=1))


def test_reassinar_depois_de_cancelar_reativa(app, fazer_usuario):
    u = fazer_usuario()
    contas.assinar(u, "mensal")
    contas.cancelar(u)
    a = contas.assinar(u, "anual")
    assert a.status == "ativa" and Assinatura.query.count() == 1


def test_cancelar_pela_conta(client, fazer_usuario, logar):
    u = fazer_usuario(plano="pro")
    logar(client, u)
    assert "Cancelar assinatura" in client.get("/conta").get_data(as_text=True)
    client.post("/conta/cancelar")
    assert u.assinaturas[0].status == "cancelada"


def test_pedido_institucional_grava(client):
    dados = {"nome": "Bia", "orgao": "Câmara de Paço", "municipio": "Paço do Lumiar", "email": "bia@camara.gov.br",
             "mensagem": "Queremos uma demonstração."}
    r = client.post("/planos/institucional", data=dados)
    assert r.status_code == 200 and "Recebemos" in r.get_data(as_text=True)
    assert PedidoInstitucional.query.one().municipio == "Paço do Lumiar"


def test_pedido_institucional_invalido(client):
    r = client.post("/planos/institucional", data={"nome": "Bia", "orgao": "", "municipio": "X", "email": "sem-arroba"})
    assert r.status_code == 200 and PedidoInstitucional.query.count() == 0
    assert "Preencha" in r.get_data(as_text=True)
