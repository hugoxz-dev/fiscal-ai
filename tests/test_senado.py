import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import requests

from app.models import DespesaParlamentar, Politico, Proposicao
from app.services.coletores.senado import coletar_senado

FIX = Path(__file__).parent / "fixtures"
DE, ATE = date(2026, 1, 1), date(2026, 12, 31)


def _fix(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


def fazer_get(lista=None):
    lista = lista or _fix("senado_lista.json")

    def get(url, params=None):
        params = params or {}
        if url.endswith("/lista/atual.json"):
            return lista
        if url.endswith("/processo"):
            if params.get("codigoParlamentarAutor") == 5001 and params.get("sigla") == "PL":
                return _fix("senado_processos.json")
            return []
        raise AssertionError(url)

    return get


def baixar(url):
    if url.endswith("2026.csv"):
        return (FIX / "senado_ceaps.csv").read_bytes().decode("latin-1")
    return ""


def rodar(**kw):
    kw.setdefault("get", fazer_get())
    kw.setdefault("baixar_texto", baixar)
    return coletar_senado(DE, ATE, pausa=0, **kw)


def test_coletar_senado_so_ma(app):
    with app.app_context():
        assert rodar() == 2
        assert Politico.query.filter(Politico.id_senado.isnot(None)).count() == 2
        p = Politico.query.filter_by(id_senado=5001).one()
        assert p.cargo == "Senador" and p.uf == "MA" and p.em_exercicio
        assert p.nome == "Beltrano de Sousa Lima" and p.nome_urna == "Beltrano Sousa"
        assert p.partido == "PY" and p.ano_eleicao is None and p.foto_url.endswith("5001.jpg")
        assert "BELTRANO" in p.nome_busca


def test_parlamentar_unico_como_dict(app):
    with app.app_context():
        lista = _fix("senado_lista.json")
        um = lista["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"][0]
        lista["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"] = um
        assert rodar(get=fazer_get(lista)) == 1


def test_identificacao_vira_sigla_numero_ano(app):
    with app.app_context():
        rodar()
        pr = Proposicao.query.one()  # o de 2019 fica fora por data
        assert pr.casa == "Senado" and pr.id_externo == 9001
        assert (pr.sigla_tipo, pr.numero, pr.ano) == ("PL", 896, 2023)
        assert pr.data_apresentacao == date(2026, 3, 10)
        assert pr.url == "https://www25.senado.leg.br/web/atividade/materias/-/materia/9001"


def test_ceaps_pula_linha_de_atualizacao_e_filtra_senador(app):
    with app.app_context():
        rodar()
        assert DespesaParlamentar.query.count() == 3
        d = DespesaParlamentar.query.filter_by(cod_documento="2001").one()
        assert d.valor == Decimal("399.44") and d.documento == "66970229013226"
        assert d.ano == 2026 and d.mes == 3 and d.fornecedor_nome == "IMOBILIÁRIA SÃO LUÍS LTDA"
        assert d.tipo == "Aluguel de imóveis"
        assert DespesaParlamentar.query.filter_by(cod_documento="2002").one().valor == Decimal("1250.00")
        assert DespesaParlamentar.query.filter_by(cod_documento="2004").first() is None


def test_idempotente(app):
    with app.app_context():
        rodar()
        rodar()
        assert Politico.query.count() == 2
        assert DespesaParlamentar.query.count() == 3
        assert Proposicao.query.count() == 1


def test_nao_sobrescreve_cpf_e_ano_eleicao(app):
    with app.app_context():
        rodar()
        from app.extensions import db
        p = Politico.query.filter_by(id_senado=5001).one()
        p.cpf, p.ano_eleicao, p.sq_candidato = "12345678909", 2022, "99"
        db.session.commit()
        rodar()
        p = Politico.query.filter_by(id_senado=5001).one()
        assert (p.cpf, p.ano_eleicao, p.sq_candidato) == ("12345678909", 2022, "99")


def test_lista_com_falha_ou_vazia_nao_desativa(app):
    with app.app_context():
        rodar()

        def get_falho(url, params=None):
            raise requests.ConnectionError("fora")

        assert rodar(get=get_falho) == 0
        vazia = {"ListaParlamentarEmExercicio": {"Parlamentares": {}}}
        assert rodar(get=fazer_get(vazia)) == 0
        assert all(p.em_exercicio for p in Politico.query.all())


def test_quem_saiu_fica_fora_de_exercicio(app):
    with app.app_context():
        rodar()
        lista = _fix("senado_lista.json")
        pars = lista["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
        lista["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"] = pars[:1]
        rodar(get=fazer_get(lista))
        assert Politico.query.filter_by(id_senado=5002).one().em_exercicio is False
        assert Politico.query.filter_by(id_senado=5001).one().em_exercicio is True


def test_erro_em_processo_ou_ceaps_nao_derruba(app):
    with app.app_context():
        base = fazer_get()

        def get(url, params=None):
            if url.endswith("/processo"):
                raise requests.ConnectionError("x")
            return base(url, params)

        def baixar_ruim(url):
            raise requests.ConnectionError("y")

        assert rodar(get=get, baixar_texto=baixar_ruim) == 2
        assert Proposicao.query.count() == 0 and DespesaParlamentar.query.count() == 0
