from datetime import datetime

import pytest

from app.extensions import db
from app.models import Alerta, Fornecedor, Politico, Seguido, Socio
from app.services import monitoramento as mon
from app.services.texto import cpf_meio, normalizar

ANTES, DEPOIS, REF = datetime(2024, 12, 1), datetime(2025, 2, 1), datetime(2025, 1, 1)


def _seguir_em(u, tipo, alvo_id, quando=REF):
    s = mon.seguir(u, tipo, alvo_id)
    s.criado_em = quando
    db.session.commit()
    return s


def test_seguir_idempotente(app, fazer_usuario, fazer_contrato):
    u, c = fazer_usuario(plano="pro"), fazer_contrato()
    mon.seguir(u, "fornecedor", c.fornecedor_id)
    mon.seguir(u, "fornecedor", c.fornecedor_id)
    assert Seguido.query.count() == 1 and mon.segue(u, "fornecedor", c.fornecedor_id)
    mon.deixar(u, "fornecedor", c.fornecedor_id)
    assert not mon.segue(u, "fornecedor", c.fornecedor_id)


def test_seguir_alvo_invalido(app, fazer_usuario):
    u = fazer_usuario(plano="pro")
    with pytest.raises(LookupError):
        mon.seguir(u, "fornecedor", 9999)
    with pytest.raises(ValueError):
        mon.seguir(u, "orgao", 1)


def test_rota_seguir_e_404(client, fazer_usuario, logar, fazer_contrato):
    c = fazer_contrato()
    logar(client, fazer_usuario(plano="pro"))
    r = client.post(f"/seguir/fornecedor/{c.fornecedor_id}", data={"next": f"/fornecedores/{c.fornecedor_id}"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/fornecedores/{c.fornecedor_id}")
    assert Seguido.query.count() == 1
    assert client.post("/seguir/fornecedor/9999").status_code == 404
    assert client.post("/seguir/orgao/1").status_code == 404


def test_seguir_sem_pro_vai_para_planos(client, fazer_usuario, logar, fazer_contrato):
    c = fazer_contrato()
    logar(client, fazer_usuario())
    r = client.post(f"/seguir/fornecedor/{c.fornecedor_id}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/planos")


def test_novidade_de_contrato_e_alerta(app, fazer_usuario, fazer_contrato):
    u = fazer_usuario(plano="pro")
    velho, novo = fazer_contrato(), fazer_contrato()
    velho.coletado_em, novo.coletado_em = ANTES, DEPOIS
    velho.alertas.append(Alerta(regra_codigo="dispensa_limite", pontos=10, evidencia={}, criado_em=ANTES))
    velho.alertas.append(Alerta(regra_codigo="fracionamento", pontos=10, evidencia={}, criado_em=DEPOIS))
    db.session.commit()
    _seguir_em(u, "fornecedor", novo.fornecedor_id)
    [item] = mon.novidades(u)
    assert [c.id for c in item["contratos"]] == [novo.id]
    assert [a.regra_codigo for a in item["alertas"]] == ["fracionamento"]
    assert mon.contar(u) == 2


def test_ultima_visita_vale_mais_que_data_de_seguir(app, fazer_usuario, fazer_contrato):
    u = fazer_usuario(plano="pro")
    c = fazer_contrato()
    c.coletado_em = DEPOIS
    _seguir_em(u, "fornecedor", c.fornecedor_id)
    u.ultima_visita_monitoramento = datetime(2025, 3, 1)
    db.session.commit()
    assert mon.contar(u) == 0


def test_abrir_painel_zera_contador(client, fazer_usuario, logar, fazer_contrato):
    u = fazer_usuario(plano="pro")
    c = fazer_contrato()
    c.coletado_em = DEPOIS
    _seguir_em(u, "fornecedor", c.fornecedor_id)
    logar(client, u)
    assert 'class="contador-novidades"' in client.get("/").get_data(as_text=True)
    html = client.get("/conta/monitoramento").get_data(as_text=True)
    assert "EMPRESA PADRAO LTDA" in html and "1 contrato novo" in html
    assert mon.contar(u) == 0


def test_painel_exige_pro(client, fazer_usuario, logar):
    logar(client, fazer_usuario())
    assert client.get("/conta/monitoramento").headers["Location"].endswith("/planos")


def test_politico_so_conta_ligacao_confirmada(app, fazer_usuario, fazer_contrato):
    cpf = "11122233344"
    confirmado = Fornecedor(documento="11111111000111", nome="CONFIRMADA LTDA", tipo="PJ")
    so_nome = Fornecedor(documento="22222222000122", nome="HOMONIMO LTDA", tipo="PJ")
    db.session.add_all([confirmado, so_nome,
                        Socio(fornecedor=confirmado, nome="Beltrano da Silva", nome_norm=normalizar("Beltrano da Silva"),
                              cpf_meio=cpf_meio(cpf)),
                        Socio(fornecedor=so_nome, nome="Beltrano da Silva", nome_norm=normalizar("Beltrano da Silva"),
                              cpf_meio=None)])
    p = Politico(nome="Beltrano da Silva", cpf=cpf, cargo="Vereador", uf="MA")
    db.session.add(p)
    db.session.commit()
    c1, c2 = fazer_contrato(fornecedor=confirmado), fazer_contrato(fornecedor=so_nome)
    c1.coletado_em = c2.coletado_em = DEPOIS
    db.session.commit()
    u = fazer_usuario(plano="pro")
    _seguir_em(u, "politico", p.id)
    [item] = mon.novidades(u)
    assert [c.id for c in item["contratos"]] == [c1.id] and item["alertas"] == []


def test_fornecedor_mostra_botao_com_cadeado_sem_login(client, fazer_contrato):
    c = fazer_contrato()
    html = client.get(f"/fornecedores/{c.fornecedor_id}").get_data(as_text=True)
    assert "Seguir" in html and "/planos" in html


def test_fornecedor_mostra_deixar_de_seguir_para_pro(client, fazer_usuario, logar, fazer_contrato):
    c = fazer_contrato()
    u = fazer_usuario(plano="pro")
    mon.seguir(u, "fornecedor", c.fornecedor_id)
    logar(client, u)
    assert "Deixar de seguir" in client.get(f"/fornecedores/{c.fornecedor_id}").get_data(as_text=True)


def test_politico_mostra_botao_seguir(client):
    p = Politico(nome="Fulano", cargo="Vereador", uf="MA", em_exercicio=True)
    db.session.add(p)
    db.session.commit()
    assert "Seguir" in client.get(f"/politicos/{p.id}").get_data(as_text=True)
