from decimal import Decimal

from app.services.texto import cpf_meio, cpf_valido, dinheiro_br, normalizar


def test_normalizar():
    assert normalizar("  São  Luís ") == "SAO LUIS"
    assert normalizar(None) == ""


def test_cpf_meio():
    assert cpf_meio("12368284799") == "682847"
    assert cpf_meio("***682847**") == "682847"
    assert cpf_meio("12345678000199") is None and cpf_meio("-4") is None and cpf_meio(None) is None


def test_cpf_valido():
    assert cpf_valido("02898953407") == "02898953407"
    assert cpf_valido("-4") is None and cpf_valido("#NULO") is None


def test_dinheiro_br():
    assert dinheiro_br("893.200,00") == Decimal("893200.00")
    assert dinheiro_br("800,00") == Decimal("800.00")
    assert dinheiro_br(-419.94) == Decimal("-419.94")
    assert dinheiro_br("") is None and dinheiro_br("#NULO") is None
