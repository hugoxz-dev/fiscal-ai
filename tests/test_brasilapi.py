import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import Fornecedor
from app.services.coletores.brasilapi import enriquecer_fornecedores, parse_cnpj

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
