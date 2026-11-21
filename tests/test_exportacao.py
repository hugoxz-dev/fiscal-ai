import csv
import io
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Alerta, Fornecedor, Politico
from app.services import exportacao


@pytest.fixture
def pro_logado(client, fazer_usuario, logar):
    u = fazer_usuario(plano="pro")
    logar(client, u)
    return u


def _linhas(r):
    texto = r.get_data().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto), delimiter=";"))


def test_csv_respeita_filtro(client, pro_logado, fazer_contrato):
    fazer_contrato(objeto="Obra grande", nivel="Alto", score=70, valor_global=Decimal("1234.50"))
    fazer_contrato(objeto="Papel", nivel="Baixo")
    r = client.get("/contratos.csv?nivel=Alto")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert r.get_data().startswith(b"\xef\xbb\xbf")  # BOM: Excel abre com acentos
    cab, *linhas = _linhas(r)
    assert "Objeto" in cab and "Valor global" in cab
    assert len(linhas) == 1 and "Obra grande" in linhas[0] and "1234,50" in linhas[0]


def test_csv_mascara_cpf(client, pro_logado, fazer_contrato):
    pf = Fornecedor(documento="12345678901", nome="FULANO PF", tipo="PF")
    fazer_contrato(fornecedor=pf)
    corpo = client.get("/contratos.csv").get_data().decode("utf-8-sig")
    assert "***.456.789-**" in corpo and "12345678901" not in corpo


def test_csv_exige_pro(client, fazer_usuario, logar):
    assert client.get("/contratos.csv").status_code == 302
    logar(client, fazer_usuario())
    assert client.get("/contratos.csv").headers["Location"].endswith("/planos")


def test_csv_alertas_do_fornecedor(client, pro_logado, fazer_contrato):
    c = fazer_contrato()
    c.alertas.append(Alerta(regra_codigo="dispensa_limite", pontos=20, evidencia={"valor": "1"}))
    db.session.commit()
    cab, *linhas = _linhas(client.get(f"/fornecedores/{c.fornecedor_id}/alertas.csv"))
    assert "Regra" in cab and len(linhas) == 1 and "dispensa_limite" in linhas[0]


def test_relatorio_fornecedor_tem_aviso_e_data(client, pro_logado, fazer_contrato):
    c = fazer_contrato()
    html = client.get(f"/relatorio/fornecedor/{c.fornecedor_id}").get_data(as_text=True)
    assert "Fiscal AI — Relatório" in html and "Gerado em" in html and "não constituem acusação" in html
    assert "window.print()" in html and "EMPRESA PADRAO LTDA" in html


def test_relatorios_contrato_e_politico(client, pro_logado, fazer_contrato):
    c = fazer_contrato()
    p = Politico(nome="Fulano", cargo="Vereador", uf="MA")
    db.session.add(p)
    db.session.commit()
    assert client.get(f"/relatorio/contrato/{c.id}").status_code == 200
    assert client.get(f"/relatorio/politico/{p.id}").status_code == 200
    assert client.get("/relatorio/contrato/9999").status_code == 404


def test_relatorio_exige_pro(client, fazer_contrato):
    c = fazer_contrato()
    assert client.get(f"/relatorio/contrato/{c.id}").status_code == 302


def test_botoes_com_cadeado_para_quem_nao_e_pro(client, fazer_contrato):
    c = fazer_contrato()
    html = client.get("/contratos").get_data(as_text=True)
    assert "Baixar CSV" in html and "bloqueado" in html
    assert "Relatório para impressão" in client.get(f"/contratos/{c.id}").get_data(as_text=True)


def test_botao_csv_leva_filtros_para_pro(client, pro_logado, fazer_contrato):
    fazer_contrato()
    html = client.get("/contratos?nivel=Alto").get_data(as_text=True)
    assert "/contratos.csv?nivel=Alto" in html


def test_contrato_dict_formato(app, fazer_contrato):
    c = fazer_contrato(valor_global=Decimal("10.50"))
    with app.test_request_context():
        d = exportacao.contrato_dict(c, com_alertas=True)
    assert d["valor_global"] == "10.50" and d["data_assinatura"] == "2025-05-01"
    assert d["fornecedor"]["documento"] == "12.345.678/0001-99" and d["alertas"] == []
