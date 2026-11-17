from datetime import date
from decimal import Decimal

from app.services.analisador import analisar_todos
from app.views._filtros import cnpj, data_br, moeda

AVISO = ("Os alertas indicam indícios de risco calculados automaticamente e não constituem acusação "
         "ou prova de irregularidade.")


def test_moeda():
    assert moeda(Decimal("1234.5")) == "R$ 1.234,50"
    assert moeda(Decimal("1000000")) == "R$ 1.000.000,00"
    assert moeda(None) == "—"


def test_data_br():
    assert data_br(date(2025, 3, 7)) == "07/03/2025"
    assert data_br(None) == "—"


def test_cnpj_formatado():
    assert cnpj("12345678000199") == "12.345.678/0001-99"


def test_cpf_mascarado():
    assert cnpj("12345678901") == "***.456.789-**"


def test_inicio_200_e_aviso(client, fazer_contrato):
    fazer_contrato(modalidade_id=8, valor_global=Decimal("90000"), objeto="Compra de cadeiras")
    analisar_todos(None)
    html = client.get("/").get_data(as_text=True)
    assert AVISO in html
    assert "Compra de cadeiras" in html
    assert "R$ 90.000,00" in html


def test_inicio_banco_vazio(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Nenhum contrato analisado ainda" in resp.get_data(as_text=True)


def test_metodologia_lista_9_regras(client):
    html = client.get("/metodologia").get_data(as_text=True)
    assert html.count('class="regra"') == 9
    assert "Lei 14.133/2021, art. 75" in html
    assert AVISO in html
