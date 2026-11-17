from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Aditivo, Contrato, ExtratoDiario, Fornecedor, Orgao, PublicacaoDiario
from app.services.coletores import diario_oficial as dom
from app.services.coletores.diario_oficial import (
    coletar_diario,
    listar_edicoes,
    segmentar_extratos,
    vincular_extratos,
)

TRECHO = (Path(__file__).parent / "fixtures" / "diario_trecho.txt").read_text(encoding="utf-8")
UUID = "Código identificador: 7000861a-763d-4780-8d39-5ce4ebb55878"


class LLMFalso:
    def __init__(self, resposta):
        self.resposta = resposta

    def extrair_extrato(self, trecho):
        return self.resposta


def _contrato(doc="12345678000199", nome="ORTOPEDIA BRASIL LTDA", valor="100000.00", numero="C1"):
    o = Orgao.query.first() or Orgao(cnpj="06307102000130", razao_social="MUNICIPIO DE SAO LUIS", esfera="M")
    f = Fornecedor.query.filter_by(documento=doc).first() or Fornecedor(documento=doc, nome=nome, tipo="PJ")
    c = Contrato(numero_controle_pncp=numero, orgao=o, fornecedor=f, valor_inicial=Decimal(valor),
                 valor_global=Decimal(valor), data_assinatura=date(2024, 9, 20))
    db.session.add(c)
    return c


def _extrato(**kw):
    pub = PublicacaoDiario.query.first() or PublicacaoDiario(url_pdf="u", data_edicao=date(2024, 9, 23))
    e = ExtratoDiario(publicacao=pub, trecho="t", **kw)
    db.session.add(e)
    return e


def test_segmenta_dois_extratos():
    blocos = segmentar_extratos(TRECHO)
    assert len(blocos) == 2
    assert blocos[0].startswith("EXTRATO DO CONTRATO N.º 547/2024")
    assert blocos[1].startswith("EXTRATO DO CONTRATO N.º 548/2024")
    assert all("PORTARIA" not in b[:200] for b in blocos)


def test_ignora_linhas_de_sumario():
    texto = "SUMÁRIO\nEXTRATO DO CONTRATO N.º 1/2024 ........................ 3\n" + UUID + "\n"
    assert segmentar_extratos(texto) == []


def test_reconhece_aditivo_e_ratificacao():
    texto = ("x\nQUINTO TERMO ADITIVO AO CONTRATO N.º 059/2020\n" + "texto " * 30 + "\n" + UUID +
             "\nRATIFICAÇÃO INEXIGIBILIDADE N.º 02/2024\n" + "texto " * 30 + "\n" + UUID)
    blocos = segmentar_extratos(texto)
    assert [b.split("\n")[0] for b in blocos] == ["QUINTO TERMO ADITIVO AO CONTRATO N.º 059/2020",
                                                   "RATIFICAÇÃO INEXIGIBILIDADE N.º 02/2024"]


def test_vincula_por_documento_e_valor(app):
    c = _contrato()
    e = _extrato(tipo="contrato", documento_fornecedor="12345678000199", valor=Decimal("100500.00"))
    db.session.commit()
    assert vincular_extratos() == 1
    assert e.contrato_id == c.id


def test_vincula_por_nome_quando_sem_cnpj(app):
    c = _contrato()
    e = _extrato(tipo="contrato", nome_fornecedor="Ortopedia Brasil Ltda.", valor=Decimal("100000.00"))
    db.session.commit()
    assert vincular_extratos() == 1
    assert e.contrato_id == c.id


def test_valor_muito_diferente_nao_vincula(app):
    _contrato()
    _extrato(tipo="contrato", documento_fornecedor="12345678000199", valor=Decimal("150000.00"))
    db.session.commit()
    assert vincular_extratos() == 0


def test_aditivo_de_fornecedor_com_contrato_unico_vira_aditivo(app):
    c = _contrato()
    _extrato(tipo="aditivo", documento_fornecedor="12345678000199", valor=Decimal("30000.00"))
    db.session.commit()
    assert vincular_extratos() == 1
    a = Aditivo.query.one()
    assert a.contrato_id == c.id and a.origem == "diario" and a.valor_acrescimo == Decimal("30000.00")
    assert vincular_extratos() == 0  # idempotente


def test_aditivo_ambiguo_nao_vincula(app):
    _contrato(numero="C1")
    _contrato(numero="C2", valor="50000.00")
    _extrato(tipo="aditivo", documento_fornecedor="12345678000199", valor=Decimal("30000.00"))
    db.session.commit()
    assert vincular_extratos() == 0


def _arquivo(paginas):
    def get(url, params=None):
        assert url.endswith("/api/portal/editions/archive")
        return paginas.get(params["page"], {"editions": [], "total_pages": len(paginas)})
    return get


EDICOES = {
    1: {"total_pages": 2, "editions": [
        {"source": "legacy", "id": 3, "edition_number": "ed3.pdf", "edition_date": "2025-02-10T00:00:00.000Z",
         "pdf_download_url": "/uploads/3.pdf"},
        {"source": "legacy", "id": 2, "edition_number": "ed2.pdf", "edition_date": "2025-01-20T00:00:00.000Z",
         "pdf_download_url": "/uploads/2.pdf"}]},
    2: {"total_pages": 2, "editions": [
        {"source": "legacy", "id": 1, "edition_number": "ed1.pdf", "edition_date": "2024-12-30T00:00:00.000Z",
         "pdf_download_url": "/uploads/1.pdf"}]},
}


def test_listar_edicoes_filtra_periodo():
    eds = listar_edicoes(date(2025, 1, 1), date(2025, 1, 31), get=_arquivo(EDICOES))
    assert [e["numero_edicao"] for e in eds] == ["ed2.pdf"]
    assert eds[0]["url_pdf"] == "https://diariooficial.saoluis.ma.gov.br/uploads/2.pdf"
    assert eds[0]["data_edicao"] == date(2025, 1, 20)


def test_llm_indisponivel_mantem_publicacao(app, monkeypatch):
    monkeypatch.setattr(dom, "texto_da_edicao", lambda edicao, get, pasta: TRECHO)
    n = coletar_diario(date(2025, 1, 1), date(2025, 1, 31), LLMFalso(None), get=_arquivo(EDICOES))
    assert n == 0
    pub = PublicacaoDiario.query.one()
    assert pub.processado is False and pub.texto.startswith(TRECHO[:50])


def test_coleta_extrai_e_nao_duplica(app, monkeypatch):
    monkeypatch.setattr(dom, "texto_da_edicao", lambda edicao, get, pasta: TRECHO)
    llm = LLMFalso({"tipo": "contrato", "documento_fornecedor": None, "nome_fornecedor": "ORTOPEDIA BRASIL LTDA",
                    "valor": Decimal("291200.00"), "objeto": "cadeiras de rodas"})
    assert coletar_diario(date(2025, 1, 1), date(2025, 1, 31), llm, get=_arquivo(EDICOES)) == 2
    assert coletar_diario(date(2025, 1, 1), date(2025, 1, 31), llm, get=_arquivo(EDICOES)) == 0
    assert ExtratoDiario.query.count() == 2
    assert PublicacaoDiario.query.one().processado is True


def test_download_pdf_usa_user_agent_do_projeto(tmp_path, monkeypatch):
    agentes = []

    class Resp:
        content = b"%PDF"
        def raise_for_status(self):
            pass

    def get_falso(self, url, **kw):
        agentes.append(self.headers["User-Agent"])
        return Resp()

    monkeypatch.setattr(dom.requests.Session, "get", get_falso)
    monkeypatch.setattr(dom, "extrair_texto_pdf", lambda caminho: "ok")
    ed = {"id": 1, "fonte": "legacy", "url_pdf": "https://x/1.pdf"}
    assert dom.texto_da_edicao(ed, None, tmp_path) == "ok"
    assert agentes and not agentes[0].startswith("python-requests")
