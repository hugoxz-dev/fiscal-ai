import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import DespesaParlamentar, Politico, Proposicao
from app.services.coletores.camara import coletar_camara

FIX = Path(__file__).parent / "fixtures"


def _fix(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


def fazer_get(lista=None):
    lista = lista or _fix("camara_deputados.json")
    vazio = {"dados": [], "links": []}

    def get(url, params=None):
        params = params or {}
        if url.endswith("/deputados"):
            return lista if params.get("pagina", 1) == 1 else vazio
        if url.endswith("/despesas"):
            if not url.endswith("/101/despesas") or params.get("pagina", 1) > 1:
                return vazio
            return _fix("camara_despesas.json") if params.get("ano") == 2026 else vazio
        if url.endswith("/proposicoes"):
            if params.get("idDeputadoAutor") != 101 or params.get("pagina", 1) > 1:
                return vazio
            return _fix("camara_proposicoes.json")
        return _fix("camara_deputado.json")

    return get


def test_coletar_camara_cria_deputados_com_cpf(app):
    with app.app_context():
        n = coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)
        assert n == 2
        p = Politico.query.filter_by(id_camara=101).one()
        assert p.cpf == "12345678909" and p.nome == "FULANO DE TAL SILVA"
        assert p.nome_urna == "Fulano de Tal" and p.partido == "PX"
        assert p.cargo == "Deputado Federal" and p.uf == "MA" and p.em_exercicio
        assert p.ano_eleicao == 2022 and p.foto_url.endswith("101.jpg")
        assert "FULANO" in p.nome_busca


def test_despesas_e_proposicoes_gravadas(app):
    with app.app_context():
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)
        d = DespesaParlamentar.query.filter_by(cod_documento="7771").one()
        assert d.valor == Decimal("1500.50") and d.documento == "12345678000199"
        assert d.ano == 2026 and d.mes == 3 and d.fornecedor_nome == "GRAFICA EXEMPLO LTDA"
        assert DespesaParlamentar.query.filter_by(cod_documento="7772").one().documento == ""
        pr = Proposicao.query.one()
        assert pr.casa == "Câmara" and pr.id_externo == 2500001 and pr.sigla_tipo == "PL"
        assert pr.data_apresentacao == date(2026, 7, 7)
        assert pr.url == "https://www.camara.leg.br/propostas-legislativas/2500001"


def test_idempotente(app):
    with app.app_context():
        for _ in range(2):
            coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)
        assert Politico.query.count() == 2
        assert DespesaParlamentar.query.count() == 2
        assert Proposicao.query.count() == 1


def test_quem_saiu_fica_fora_de_exercicio(app):
    with app.app_context():
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)
        so_um = {"dados": [{"id": 101}], "links": []}
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(so_um), pausa=0)
        assert Politico.query.filter_by(id_camara=102).one().em_exercicio is False
        assert Politico.query.filter_by(id_camara=101).one().em_exercicio is True


def test_lista_com_falha_nao_desativa_ninguem(app):
    import requests

    with app.app_context():
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)

        def get_falho(url, params=None):
            raise requests.ConnectionError("fora do ar")

        assert coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=get_falho, pausa=0) == 0
        assert all(p.em_exercicio for p in Politico.query.all())


def test_detalhe_vazio_ou_com_erro_pula_deputado(app):
    import requests

    with app.app_context():
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=fazer_get(), pausa=0)
        base = fazer_get()

        def get(url, params=None):
            if url.endswith("/deputados/101"):
                return None
            if url.endswith("/deputados/102"):
                raise requests.ConnectionError("x")
            return base(url, params)

        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=get, pausa=0)
        p = Politico.query.filter_by(id_camara=101).one()
        assert p.nome == "FULANO DE TAL SILVA" and p.cpf == "12345678909"


def test_item_repetido_e_codigo_longo_viram_uma_linha(app):
    longo = "980239B8-F7B1-4971-BB6C-A49FACCED137"  # 36 chars; a coluna guarda 30
    item = {"ano": 2026, "mes": 3, "tipoDespesa": "PASSAGEM", "codDocumento": longo,
            "nomeFornecedor": "LATAM", "cnpjCpfFornecedor": None, "valorLiquido": 186.0, "urlDocumento": None}
    pagina = {"dados": [item, dict(item)], "links": []}
    base = fazer_get()

    def get(url, params=None):
        if url.endswith("/101/despesas") and (params or {}).get("ano") == 2026 and params.get("pagina", 1) == 1:
            return pagina
        return base(url, params)

    with app.app_context():
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=get, pausa=0)
        coletar_camara(date(2026, 1, 1), date(2026, 12, 31), get=get, pausa=0)
        ds = DespesaParlamentar.query.filter_by(valor=Decimal("186.00")).all()
        assert len(ds) == 1 and ds[0].cod_documento == longo[:30]
