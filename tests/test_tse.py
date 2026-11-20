import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import BemDeclarado, Doacao, Politico
from app.services.coletores.tse import coletar_tse, ler_csv

FIX = Path(__file__).parent / "fixtures" / "tse"


def abrir_falso(url, membro):
    caminho = FIX / membro
    if not caminho.exists():
        raise KeyError(membro)
    return open(caminho, encoding="latin-1", newline="")


def test_ler_csv_nulos_e_latin1():
    arq = io.StringIO('"A";"B";"C";"D"\r\n"#NULO";"-4";"São Luís";"#NULO#"\r\n')
    linha = next(ler_csv(arq))
    assert linha == {"A": None, "B": None, "C": "São Luís", "D": None}


def test_coletar_tse_municipais(app):
    coletar_tse(abrir_falso)
    ps = Politico.query.all()
    assert len(ps) == 3
    assert all(p.cpf is None and p.ano_eleicao == 2024 and p.municipio == "São Luís" for p in ps)
    assert {p.cargo for p in ps} == {"Prefeito", "Vereador"}
    assert all(p.nome_busca for p in ps)


def test_coletar_tse_vincula_federal_por_cpf_e_por_nome(app):
    dep = Politico(nome="Outro Nome", cargo="Deputado Federal", uf="MA", id_camara=1, cpf="12345678901")
    sen = Politico(nome="Joao do Senado", cargo="Senador", uf="MA", id_senado=2)
    db.session.add_all([dep, sen])
    db.session.commit()
    coletar_tse(abrir_falso)
    db.session.refresh(dep)
    db.session.refresh(sen)
    assert (dep.sq_candidato, dep.ano_eleicao) == ("2001", 2022)
    assert (sen.sq_candidato, sen.ano_eleicao) == ("2004", 2022)
    assert sen.cpf == "22222222222"


def test_coletar_tse_doacoes_e_originario(app):
    n = coletar_tse(abrir_falso)
    assert n == 4
    d = Doacao.query.filter_by(sq_receita="5001").one()
    assert d.valor == Decimal("800.00") and d.data == date(2024, 9, 15)
    assert d.documento == "11122233344" and d.originario is False
    assert d.nome_norm == "JOAO DA PADARIA"
    o = Doacao.query.filter_by(originario=True).one()
    assert o.documento == "99988877766" and o.politico.nome.startswith("MARIA")
    bem = BemDeclarado.query.filter_by(tipo="Veículo").one()
    assert bem.valor == Decimal("85000.50")


def test_coletar_tse_idempotente(app):
    coletar_tse(abrir_falso)
    antes = (Politico.query.count(), Doacao.query.count(), BemDeclarado.query.count())
    coletar_tse(abrir_falso)
    assert (Politico.query.count(), Doacao.query.count(), BemDeclarado.query.count()) == antes
    assert antes[1] == 4 and antes[2] == 3
