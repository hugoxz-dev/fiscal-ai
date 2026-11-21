from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Alerta, ChaveApi, Fornecedor, UsoApi
from app.services import api_chaves, contas


@pytest.fixture
def chave_pro(app, fazer_usuario):
    u = fazer_usuario(plano="pro")
    return u, api_chaves.gerar(u)


def _get(client, url, chave):
    return client.get(url, headers={"X-API-Key": chave} if chave else {})


def test_api_sem_chave_401(client):
    r = client.get("/api/v1/contratos")
    assert r.status_code == 401 and r.is_json and "chave" in r.get_json()["erro"]


def test_api_chave_invalida_401(client):
    assert _get(client, "/api/v1/contratos", "fai_errada").status_code == 401


def test_api_chave_revogada_401(client, chave_pro):
    u, chave = chave_pro
    api_chaves.revogar(u)
    assert _get(client, "/api/v1/contratos", chave).status_code == 401


def test_gerar_de_novo_revoga_a_anterior(client, chave_pro):
    u, velha = chave_pro
    nova = api_chaves.gerar(u)
    assert _get(client, "/api/v1/contratos", velha).status_code == 401
    assert _get(client, "/api/v1/contratos", nova).status_code == 200


def test_api_pro_vencido_403(client, fazer_usuario):
    u = fazer_usuario(plano="pro", fim=date.today() - timedelta(days=1))
    chave = api_chaves.gerar(u)
    r = _get(client, "/api/v1/contratos", chave)
    assert r.status_code == 403 and r.get_json() == {"erro": "assinatura Pro inativa"}


def test_api_limite_429(client, chave_pro):
    u, chave = chave_pro
    db.session.add(UsoApi(chave_id=u.chaves[0].id, dia=date.today(), chamadas=1000))
    db.session.commit()
    r = _get(client, "/api/v1/contratos", chave)
    assert r.status_code == 429 and "1000" in r.get_json()["erro"]


def test_api_institucional_sem_limite(client, fazer_usuario):
    u = fazer_usuario(plano="institucional")
    chave = api_chaves.gerar(u)
    db.session.add(UsoApi(chave_id=u.chaves[0].id, dia=date.today(), chamadas=5000))
    db.session.commit()
    r = _get(client, "/api/v1/contratos", chave)
    assert r.status_code == 200 and r.headers["X-Limite-Diario"] == "ilimitado"


def test_api_conta_uso_e_cabecalhos(client, chave_pro):
    u, chave = chave_pro
    _get(client, "/api/v1/contratos", chave)
    r = _get(client, "/api/v1/contratos", chave)
    assert r.headers["X-Limite-Diario"] == "1000" and r.headers["X-Chamadas-Hoje"] == "2"
    assert api_chaves.registrar_uso(u.chaves[0]) == 3


def test_api_contratos_formato_e_cpf_mascarado(client, chave_pro, fazer_contrato):
    _, chave = chave_pro
    fazer_contrato(fornecedor=Fornecedor(documento="12345678901", nome="FULANO PF", tipo="PF"), nivel="Alto")
    fazer_contrato(nivel="Baixo")
    r = _get(client, "/api/v1/contratos?nivel=Alto", chave)
    corpo = r.get_json()
    assert corpo["total"] == 1 and corpo["pagina"] == 1 and len(corpo["itens"]) == 1
    assert corpo["itens"][0]["fornecedor"]["documento"] == "***.456.789-**"
    assert "12345678901" not in r.get_data(as_text=True)


def test_api_paginacao_limitada(client, chave_pro, fazer_contrato):
    _, chave = chave_pro
    for _ in range(3):
        fazer_contrato()
    corpo = _get(client, "/api/v1/contratos?por_pagina=2&pagina=2", chave).get_json()
    assert corpo["total"] == 3 and len(corpo["itens"]) == 1 and corpo["por_pagina"] == 2
    assert _get(client, "/api/v1/contratos?por_pagina=5000", chave).get_json()["por_pagina"] == 100


def test_api_contrato_e_fornecedor(client, chave_pro, fazer_contrato):
    _, chave = chave_pro
    c = fazer_contrato()
    c.alertas.append(Alerta(regra_codigo="dispensa_limite", pontos=20, evidencia={}))
    db.session.commit()
    d = _get(client, f"/api/v1/contratos/{c.id}", chave).get_json()
    assert d["alertas"][0]["regra_codigo"] == "dispensa_limite"
    f = _get(client, f"/api/v1/fornecedores/{c.fornecedor_id}", chave).get_json()
    assert f["nome"] == "EMPRESA PADRAO LTDA" and f["ligacoes"] == [] and len(f["alertas"]) == 1


def test_api_alertas_filtra_por_regra(client, chave_pro, fazer_contrato):
    _, chave = chave_pro
    c = fazer_contrato()
    c.alertas.extend([Alerta(regra_codigo="dispensa_limite", pontos=20, evidencia={}),
                      Alerta(regra_codigo="fracionamento", pontos=20, evidencia={})])
    db.session.commit()
    corpo = _get(client, "/api/v1/alertas?regra=fracionamento", chave).get_json()
    assert corpo["total"] == 1 and corpo["itens"][0]["contrato_id"] == c.id


def test_api_404_em_json(client, chave_pro):
    _, chave = chave_pro
    r = _get(client, "/api/v1/contratos/9999", chave)
    assert r.status_code == 404 and r.is_json


def test_chave_completa_nao_fica_no_banco(app, chave_pro):
    _, chave = chave_pro
    k = ChaveApi.query.one()
    assert chave.startswith("fai_") and k.prefixo == chave[:8]
    assert chave not in (k.chave_hash, k.prefixo)


def test_conta_gera_e_mostra_chave_uma_vez(client, fazer_usuario, logar):
    u = fazer_usuario(plano="pro")
    logar(client, u)
    r = client.post("/conta/chave", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert 'class="chave"' in html and "fai_" in html
    assert 'class="chave"' not in client.get("/conta").get_data(as_text=True)
    client.post("/conta/chave/revogar")
    assert ChaveApi.query.one().revogada_em is not None


def test_conta_chave_exige_pro(client, fazer_usuario, logar):
    logar(client, fazer_usuario())
    assert client.post("/conta/chave").headers["Location"].endswith("/planos")


def test_api_docs_publica(client):
    html = client.get("/api").get_data(as_text=True)
    assert "X-API-Key" in html and "/api/v1/contratos" in html


def test_api_ignora_csrf(app, chave_pro):
    # API é somente leitura (GET); um POST nela não deve virar 400 de CSRF, e sim 405
    app.config["CSRF_ATIVO"] = True
    _, chave = chave_pro
    assert app.test_client().post("/api/v1/contratos", headers={"X-API-Key": chave}).status_code == 405


def test_api_rota_inexistente_e_metodo_errado_em_json(client, chave_pro):
    _, chave = chave_pro
    r = _get(client, "/api/v1/inexistente", chave)
    assert r.status_code == 404 and r.is_json
    r = client.post("/api/v1/contratos", headers={"X-API-Key": chave})
    assert r.status_code == 405 and r.is_json
