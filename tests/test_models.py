from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Alerta, BemDeclarado, Contrato, Doacao, Fornecedor, Orgao, Politico, Socio


def _contrato(numero="06307102000130-2-000001/2025"):
    o = Orgao(cnpj="06307102000130", razao_social="PREFEITURA DE SAO LUIS", esfera="M")
    f = Fornecedor(documento="12345678000199", nome="EMPRESA X", tipo="PJ")
    return Contrato(
        numero_controle_pncp=numero, orgao=o, fornecedor=f, objeto="Aquisição de merenda",
        valor_inicial=Decimal("100000.00"), valor_global=Decimal("100000.00"),
        data_assinatura=date(2025, 3, 1),
    )


def test_contrato_com_relacoes(app):
    c = _contrato()
    db.session.add(c)
    db.session.commit()
    assert Contrato.query.one().fornecedor.nome == "EMPRESA X"
    assert c.score == 0 and c.alertas == []


def test_numero_controle_unico(app):
    db.session.add(_contrato())
    db.session.commit()
    orgao, fornecedor = Orgao.query.one(), Fornecedor.query.one()
    db.session.add(Contrato(numero_controle_pncp="06307102000130-2-000001/2025",
                            orgao=orgao, fornecedor=fornecedor))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_alerta_guarda_evidencia_json(app):
    c = _contrato()
    c.alertas.append(Alerta(regra_codigo="dispensa_limite", pontos=25, evidencia={"limite": "62725.59"}))
    db.session.add(c)
    db.session.commit()
    assert Alerta.query.one().evidencia["limite"] == "62725.59"


def test_politico_busca_e_relacoes(app):
    p = Politico(nome="Fulano de Tál", nome_urna="Fulaninho", partido="PXX", cargo="Vereador")
    p.atualizar_busca()
    assert p.nome_busca == "FULANO DE TAL FULANINHO PXX VEREADOR"
    p.bens.append(BemDeclarado(tipo="Casa", descricao="Casa", valor=Decimal("1000.00")))
    p.doacoes.append(Doacao(sq_receita="1", documento="12345678000199", nome="Empresa", nome_norm="EMPRESA",
                            valor=Decimal("10.00")))
    db.session.add(p)
    db.session.commit()
    assert len(p.bens) == 1 and len(p.doacoes) == 1


def test_socio_do_fornecedor(app):
    f = Fornecedor(documento="12345678000199", nome="EMPRESA X", tipo="PJ")
    f.socios.append(Socio(nome="Fulano", nome_norm="FULANO", cpf_meio="682847"))
    db.session.add(f)
    db.session.commit()
    assert f.socios[0].cpf_meio == "682847"
