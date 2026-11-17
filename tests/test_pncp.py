import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Aditivo, Contratacao, Contrato, Orgao
from app.services.coletores.pncp import (
    coletar_pncp,
    contar_fornecedores_resultado,
    eh_municipal_sao_luis,
    parse_contratacao,
    parse_contrato,
    parse_termo,
    upsert_aditivo,
    upsert_contratacao,
    upsert_contrato,
)

FIX = Path(__file__).parent / "fixtures"


def carregar(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


@pytest.fixture
def fixture_contratos():
    return carregar("pncp_contratos.json")["data"]


@pytest.fixture
def fixture_contratacoes():
    return carregar("pncp_contratacoes.json")["data"]


def test_parse_contrato_campos(fixture_contratos):
    d = parse_contrato(fixture_contratos[0])
    assert len(d["fornecedor"]["documento"]) in (11, 14)
    assert d["fornecedor"]["tipo"] == "PJ"
    assert isinstance(d["valor_global"], Decimal)
    assert d["data_assinatura"] == date(2025, 2, 25)
    assert d["link_pncp"] == "https://pncp.gov.br/app/contratos/06307102000130/2025/21"
    assert d["numero_controle_compra"] == "06307102000130-1-000062/2025"


def test_parse_contratacao_campos(fixture_contratacoes):
    d = parse_contratacao(fixture_contratacoes[0])
    assert d["modalidade_id"] == 6
    assert d["orgao"]["esfera"] == "M"
    assert d["link_pncp"] == "https://pncp.gov.br/app/editais/06307102000130/2025/54"
    assert d["valor_homologado"] == Decimal("1376350.50")


def test_filtra_orgao_estadual(fixture_contratos, fixture_contratacoes):
    estadual = next(i for i in fixture_contratos if i["orgaoEntidade"]["esferaId"] == "E")
    assert eh_municipal_sao_luis(estadual, "2111300") is False
    assert eh_municipal_sao_luis(fixture_contratos[0], "2111300") is True
    assert [eh_municipal_sao_luis(i, "2111300") for i in fixture_contratacoes] == [True, True, False]


def test_fornecedor_pf_por_tamanho_do_documento(fixture_contratos):
    item = dict(fixture_contratos[0], niFornecedor="12345678901", tipoPessoa="PF")
    assert parse_contrato(item)["fornecedor"]["tipo"] == "PF"


def test_upsert_nao_duplica(app, fixture_contratos):
    d = parse_contrato(fixture_contratos[0])
    upsert_contrato(d)
    upsert_contrato(d)
    db.session.commit()
    assert Contrato.query.count() == 1
    assert Orgao.query.count() == 1


def test_upsert_contrato_vincula_contratacao_existente(app, fixture_contratos):
    item = carregar("pncp_compra.json")
    upsert_contratacao(parse_contratacao(item))
    d = parse_contrato(fixture_contratos[0])
    d["numero_controle_compra"] = item["numeroControlePNCP"]
    c = upsert_contrato(d)
    db.session.commit()
    assert c.contratacao.numero_controle_pncp == item["numeroControlePNCP"]
    assert c.modalidade_id == item["modalidadeId"]


def test_parse_termo_aditivo():
    d = parse_termo(carregar("pncp_termos.json")[0])
    assert d == {"numero": "13/2024", "valor_acrescimo": Decimal("3596.84"),
                 "data": date(2024, 11, 8), "origem": "pncp"}


def test_upsert_aditivo_nao_duplica(app, fixture_contratos):
    c = upsert_contrato(parse_contrato(fixture_contratos[0]))
    t = parse_termo(carregar("pncp_termos.json")[0])
    upsert_aditivo(c, t)
    upsert_aditivo(c, t)
    db.session.commit()
    assert Aditivo.query.count() == 1


def test_contar_fornecedores_resultado():
    r = carregar("pncp_resultados.json")
    assert contar_fornecedores_resultado({1: r}) is None  # item único: sem informação de competição
    assert contar_fornecedores_resultado({1: r, 2: r}) == 1
    outro = [dict(r[0], niFornecedor="99999999000199")]
    assert contar_fornecedores_resultado({1: r, 2: outro}) == 2


def test_coletar_pncp_com_api_falsa_e_idempotente(app):
    contratacoes = carregar("pncp_contratacoes.json")
    contratos = carregar("pncp_contratos.json")
    compra = carregar("pncp_compra.json")

    def get_falso(url, params=None):
        if url.endswith("/contratacoes/publicacao"):
            return contratacoes if params["codigoModalidadeContratacao"] == 6 else None
        if url.endswith("/contratos"):
            return contratos
        if "/compras/" in url and url.count("/") == compra_barras:
            return compra
        if url.endswith("/termos"):
            return None
        if url.endswith("/itens"):
            return []
        return None

    compra_barras = "https://pncp.gov.br/api/consulta/v1/orgaos/1/compras/2024/1".count("/")
    n1 = coletar_pncp(date(2025, 3, 1), date(2025, 3, 15), "2111300", get=get_falso)
    n2 = coletar_pncp(date(2025, 3, 1), date(2025, 3, 15), "2111300", get=get_falso)
    assert n1 > 0 and n1 == n2
    assert {o.esfera for o in Orgao.query} == {"M"}
    assert Contrato.query.count() == 2
    assert Contratacao.query.count() >= 2
