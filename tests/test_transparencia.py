import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import Convenio, Emenda, Fornecedor, Politico, Sancao
from app.services.coletores.transparencia import (
    coletar_convenios,
    coletar_emendas,
    coletar_sancoes,
    parse_convenio,
    parse_sancao,
)

FIX = Path(__file__).parent / "fixtures"
CEIS = json.loads((FIX / "ceis.json").read_text(encoding="utf-8"))
CONV = json.loads((FIX / "convenios.json").read_text(encoding="utf-8"))
EMENDAS = json.loads((FIX / "emendas.json").read_text(encoding="utf-8"))


def test_parse_sancao():
    d = parse_sancao(CEIS[0], "CEIS")
    assert d["documento"] == "12345678000199"
    assert d["cadastro"] == "CEIS"
    assert d["data_inicio"] == date(2024, 3, 15) and d["data_fim"] == date(2026, 3, 15)
    assert d["orgao_sancionador"] == "Prefeitura Municipal de Imperatriz"
    assert "Impedimento" in d["descricao"]


def test_parse_convenio():
    d = parse_convenio(CONV[0])
    assert d == {"numero": "945123", "orgao_concedente": "Ministério das Cidades",
                 "objeto": "Pavimentação de vias urbanas", "valor": Decimal("1500000.00"),
                 "data_inicio": date(2025, 2, 10), "convenente_municipal": True}
    assert parse_convenio(CONV[1])["convenente_municipal"] is False


def test_sem_chave_retorna_zero(app):
    app.config["TRANSPARENCIA_API_KEY"] = ""
    db.session.add(Fornecedor(documento="12345678000199", nome="X", tipo="PJ"))
    db.session.commit()
    assert coletar_sancoes(get=None, pausa=0) == 0
    assert coletar_convenios(date(2025, 1, 1), date(2025, 3, 31), "2111300", get=None, pausa=0) == 0


def test_sancao_nao_duplica(app):
    app.config["TRANSPARENCIA_API_KEY"] = "teste"
    db.session.add(Fornecedor(documento="12345678000199", nome="X", tipo="PJ"))
    db.session.commit()

    def get_falso(url, params=None):
        return CEIS if url.endswith("/ceis") and params["pagina"] == 1 else []

    assert coletar_sancoes(get=get_falso, pausa=0) == 1
    coletar_sancoes(get=get_falso, pausa=0)
    assert Sancao.query.count() == 1


def test_convenios_so_do_municipio(app):
    app.config["TRANSPARENCIA_API_KEY"] = "teste"

    def get_falso(url, params=None):
        assert params["codigoIBGE"] == "2111300" and params["dataInicial"] == "01/01/2025"
        return CONV if params["pagina"] == 1 else []

    assert coletar_convenios(date(2025, 1, 1), date(2025, 3, 31), "2111300", get=get_falso, pausa=0) == 1
    assert Convenio.query.one().numero == "945123"


def test_data_com_texto_vira_none():
    from app.services.coletores.transparencia import _data
    assert _data("Sem informação") is None
    assert _data("31/12/2025").isoformat() == "2025-12-31"


def _federal():
    db.session.add(Politico(nome="Duda", nome_urna="Duda do Maranhão", cargo="Deputado Federal",
                            uf="MA", em_exercicio=True))
    db.session.add(Politico(nome="Sem Urna", nome_urna=None, cargo="Senador", uf="MA", em_exercicio=True))
    db.session.commit()


def test_emendas_so_sao_luis_e_do_autor(app):
    app.config["TRANSPARENCIA_API_KEY"] = "teste"
    _federal()
    chamadas = []

    def get_falso(url, params=None):
        chamadas.append(params)
        return EMENDAS if params["pagina"] == 1 else []

    assert coletar_emendas(date(2025, 1, 1), date(2025, 12, 31), get=get_falso, pausa=0) == 1
    assert all(c["ano"] == 2025 and c["nomeAutor"] == "DUDA DO MARANHAO" for c in chamadas)
    e = Emenda.query.one()
    assert e.codigo == "202571000001" and e.ano == 2025
    assert e.valor_empenhado == Decimal("893200.00") and e.valor_pago == Decimal("400000.50")


def test_emendas_idempotente(app):
    app.config["TRANSPARENCIA_API_KEY"] = "teste"
    _federal()

    def get_falso(url, params=None):
        return EMENDAS if params["pagina"] == 1 else []

    coletar_emendas(date(2025, 1, 1), date(2025, 12, 31), get=get_falso, pausa=0)
    coletar_emendas(date(2025, 1, 1), date(2025, 12, 31), get=get_falso, pausa=0)
    assert Emenda.query.count() == 1
