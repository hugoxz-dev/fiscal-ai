import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import Fornecedor, Socio
from app.services.coletores.brasilapi import (coletar_socios, enriquecer_fornecedores,
                                              parse_cnpj, parse_socios)

FIX = json.loads((Path(__file__).parent / "fixtures" / "brasilapi_cnpj.json").read_text(encoding="utf-8"))


def test_parse_cnpj():
    d = parse_cnpj(FIX)
    assert d["data_abertura"] == date(2016, 11, 23)
    assert d["capital_social"] == Decimal("20000.00")
    assert d["cnae_codigo"] == "8230001"
    assert d["cnae_descricao"].startswith("Serviços de organização")
    assert d["situacao"] == "ATIVA"


def test_pf_nao_consulta(app):
    db.session.add(Fornecedor(documento="12345678901", nome="FULANO", tipo="PF"))
    db.session.commit()

    def get_proibido(url, params=None):
        raise AssertionError("não deveria consultar CPF")

    assert enriquecer_fornecedores(get=get_proibido, pausa=0) == 0


def test_enriquece_pj_e_nao_repete(app):
    db.session.add(Fornecedor(documento="26593545000142", nome="X", tipo="PJ"))
    db.session.commit()
    chamadas = []

    def get_falso(url, params=None):
        chamadas.append(url)
        return FIX

    assert enriquecer_fornecedores(get=get_falso, pausa=0) == 1
    assert enriquecer_fornecedores(get=get_falso, pausa=0) == 0
    f = Fornecedor.query.one()
    assert f.data_abertura == date(2016, 11, 23) and f.enriquecido_em is not None
    assert chamadas == ["https://brasilapi.com.br/api/cnpj/v1/26593545000142"]


def test_cnpj_nao_encontrado_marca_e_segue(app):
    db.session.add(Fornecedor(documento="00000000000000", nome="Y", tipo="PJ"))
    db.session.commit()
    assert enriquecer_fornecedores(get=lambda url, params=None: None, pausa=0) == 0
    f = Fornecedor.query.one()
    assert f.enriquecido_em is not None and f.data_abertura is None


def test_parse_cnpj_atividades_secundarias_e_natureza():
    import json
    from pathlib import Path

    d = parse_cnpj(json.loads((Path(__file__).parent / "fixtures" / "brasilapi_cnpj.json").read_text(encoding="utf-8")))
    assert d["cnaes_secundarios"].startswith("Impressão de material para uso publicitário; ")
    assert d["natureza_juridica"] == "2062"


def test_parse_socios():
    socios = parse_socios(FIX)
    assert len(socios) == 2
    pf, pj = socios
    assert pf["nome"] == "JOSÉ DA SILVA SAURO"
    assert pf["nome_norm"] == "JOSE DA SILVA SAURO"
    assert pf["cpf_meio"] == "682847"
    assert pf["qualificacao"] == "Sócio-Administrador"
    assert pf["data_entrada"] == date(2016, 11, 23)
    assert pj["cpf_meio"] is None


def test_parse_socios_repetido_fica_so_o_primeiro():
    d = {"qsa": [{"nome_socio": "A B", "cnpj_cpf_do_socio": "***111222**", "qualificacao_socio": "Sócio"},
                 {"nome_socio": "A B", "cnpj_cpf_do_socio": "***111222**", "qualificacao_socio": "Administrador"}]}
    socios = parse_socios(d)
    assert [s["qualificacao"] for s in socios] == ["Sócio"]
    assert parse_socios({}) == []


def test_enriquecer_grava_socios(app):
    db.session.add(Fornecedor(documento="26593545000142", nome="X", tipo="PJ"))
    db.session.commit()
    enriquecer_fornecedores(get=lambda url, params=None: FIX, pausa=0)
    assert Socio.query.count() == 2


def test_coletar_socios_so_quem_falta_e_idempotente(app):
    from datetime import datetime

    db.session.add(Fornecedor(documento="26593545000142", nome="X", tipo="PJ", enriquecido_em=datetime.now()))
    db.session.add(Fornecedor(documento="00000000000191", nome="NAO ENRIQUECIDO", tipo="PJ"))
    db.session.commit()
    chamadas = []

    def get_falso(url, params=None):
        chamadas.append(url)
        return FIX

    assert coletar_socios(get=get_falso, pausa=0) == 1
    assert coletar_socios(get=get_falso, pausa=0) == 0
    assert chamadas == ["https://brasilapi.com.br/api/cnpj/v1/26593545000142"]
    assert Socio.query.count() == 2
