from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import ExtratoDiario, Fornecedor, PublicacaoDiario, Sancao
from app.services.analisador import analisar_todos


@pytest.fixture
def base(fazer_contrato):
    nova = Fornecedor(documento="11222333000144", nome="CONSTRUTORA NOVA LTDA", tipo="PJ",
                      data_abertura=date(2025, 3, 1), capital_social=Decimal("1000"))
    db.session.add(Sancao(documento="11222333000144", cadastro="CEIS", data_inicio=date(2024, 1, 1),
                          orgao_sancionador="TCE-MA", descricao="Impedimento"))
    alto = fazer_contrato(fornecedor=nova, modalidade_id=8, valor_global=Decimal("90000"),
                          objeto="Reparo de telhado", link_pncp="https://pncp.gov.br/app/contratos/x/2025/1")
    baixo = fazer_contrato(valor_global=Decimal("5000"), objeto="Compra de papel A4")
    fazer_contrato(valor_global=Decimal("6000"), objeto="Compra de canetas")
    fazer_contrato(valor_global=Decimal("7000"), objeto="Compra de grampos")
    analisar_todos(None)
    return alto, baixo


def test_filtro_nivel_alto(client, base):
    html = client.get("/contratos?nivel=Alto").get_data(as_text=True)
    assert "Reparo de telhado" in html and "Compra de papel A4" not in html


def test_ordem_padrao_por_score(client, base):
    html = client.get("/contratos").get_data(as_text=True)
    assert html.index("Reparo de telhado") < html.index("Compra de papel A4")


def test_busca_fornecedor_por_nome(client, base):
    html = client.get("/contratos?fornecedor=construtora").get_data(as_text=True)
    assert "Reparo de telhado" in html and "Compra de canetas" not in html


def test_busca_fornecedor_por_cnpj_formatado(client, base):
    html = client.get("/contratos?fornecedor=11.222.333/0001-44").get_data(as_text=True)
    assert "Reparo de telhado" in html and "Compra de canetas" not in html


def test_filtro_periodo_e_modalidade(client, base):
    html = client.get("/contratos?modalidade=8&de=2025-01-01&ate=2025-12-31").get_data(as_text=True)
    assert "Reparo de telhado" in html and "Compra de papel A4" not in html


def test_param_invalido_nao_quebra(client, base):
    resp = client.get("/contratos?de=abc&ate=2025-99-99&pagina=-1&orgao=x&modalidade=y&ordem=hack&nivel=<b>")
    assert resp.status_code == 200
    assert "Reparo de telhado" in resp.get_data(as_text=True)


def test_paginacao(client, fazer_contrato):
    for i in range(30):
        fazer_contrato(objeto=f"Item numero {i:02d}", valor_global=Decimal(1000 + i))
    analisar_todos(None)
    p1 = client.get("/contratos?ordem=valor").get_data(as_text=True)
    p2 = client.get("/contratos?ordem=valor&pagina=2").get_data(as_text=True)
    assert "Item numero 29" in p1 and "Item numero 29" not in p2
    assert "Item numero 00" in p2


def test_detalhe_mostra_evidencia_e_link_pncp(client, base):
    alto, _ = base
    html = client.get(f"/contratos/{alto.id}").get_data(as_text=True)
    assert "Fornecedor com sanção vigente" in html
    assert "Dispensa acima do limite legal" in html
    assert "62.725,59" in html or "62725.59" in html
    assert 'href="https://pncp.gov.br/app/contratos/x/2025/1"' in html


def test_detalhe_sem_explicacao(client, base):
    alto, _ = base
    assert "Explicação indisponível" in client.get(f"/contratos/{alto.id}").get_data(as_text=True)


def test_detalhe_com_explicacao_e_diario(client, base):
    alto, _ = base
    alto.explicacao = "Foram observados indícios relevantes."
    pub = PublicacaoDiario(url_pdf="https://diariooficial.saoluis.ma.gov.br/x.pdf", data_edicao=date(2025, 5, 2))
    db.session.add(ExtratoDiario(publicacao=pub, tipo="contrato", trecho="EXTRATO", contrato=alto))
    db.session.commit()
    html = client.get(f"/contratos/{alto.id}").get_data(as_text=True)
    assert "Foram observados indícios relevantes." in html
    assert 'href="https://diariooficial.saoluis.ma.gov.br/x.pdf"' in html


def test_contrato_inexistente_404(client, base):
    assert client.get("/contratos/99999").status_code == 404


def test_pagina_fornecedor(client, base):
    html = client.get("/fornecedores/11222333000144").get_data(as_text=True)
    assert "CONSTRUTORA NOVA LTDA" in html and "11.222.333/0001-44" in html
    assert "CEIS" in html and "Reparo de telhado" in html
    assert "%" in html  # concentração no órgão


def test_fornecedor_404(client, base):
    assert client.get("/fornecedores/00000000000000").status_code == 404
