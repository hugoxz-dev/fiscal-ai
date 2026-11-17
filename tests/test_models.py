from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Alerta, Contrato, Fornecedor, Orgao


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
