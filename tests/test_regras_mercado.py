from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Aditivo, Contratacao, Contrato, Fornecedor, Orgao
from app.services.regras.aditivos import AditivosExcessivos
from app.services.regras.base import Contexto
from app.services.regras.competicao import CompeticaoBaixa
from app.services.regras.concentracao import Concentracao
from app.services.regras.config import PESOS


def _ctx():
    return Contexto(contratos=Contrato.query.all(), sancoes={}, llm=None)


def _forn(doc):
    return Fornecedor(documento=doc, nome=f"F{doc[-2:]}", tipo="PJ")


def test_concentracao_40pct_dispara(fazer_contrato):
    alvo = fazer_contrato(fornecedor=_forn("11111111000111"), valor_global=Decimal("40000"))
    fazer_contrato(fornecedor=_forn("22222222000122"), valor_global=Decimal("30000"))
    fazer_contrato(fornecedor=_forn("33333333000133"), valor_global=Decimal("30000"))
    r = Concentracao(PESOS).avaliar(alvo, _ctx())
    assert r.pontos == 15
    assert r.evidencia["percentual"] == 40.0
    assert r.evidencia["total_orgao"] == "100000.00" and r.evidencia["total_fornecedor"] == "40000.00"


def test_concentracao_abaixo_do_limite_nao_dispara(fazer_contrato):
    alvo = fazer_contrato(fornecedor=_forn("11111111000111"), valor_global=Decimal("20000"))
    fazer_contrato(fornecedor=_forn("22222222000122"), valor_global=Decimal("40000"))
    fazer_contrato(fornecedor=_forn("33333333000133"), valor_global=Decimal("40000"))
    assert Concentracao(PESOS).avaliar(alvo, _ctx()) is None


def test_concentracao_orgao_com_2_contratos_nao_dispara(fazer_contrato):
    alvo = fazer_contrato(fornecedor=_forn("11111111000111"), valor_global=Decimal("90000"))
    fazer_contrato(fornecedor=_forn("22222222000122"), valor_global=Decimal("10000"))
    assert Concentracao(PESOS).avaliar(alvo, _ctx()) is None


def _compra(modalidade, qtd):
    orgao = Orgao.query.first() or Orgao(cnpj="06307102000130", razao_social="MUNICIPIO DE SAO LUIS", esfera="M")
    c = Contratacao(numero_controle_pncp=f"X-{modalidade}-{qtd}", orgao=orgao, modalidade_id=modalidade,
                    qtd_fornecedores_resultado=qtd)
    db.session.add(c)
    return c


def test_competicao_pregao_um_fornecedor_dispara(fazer_contrato):
    c = fazer_contrato(contratacao=_compra(6, 1), modalidade_id=6)
    r = CompeticaoBaixa(PESOS).avaliar(c, _ctx())
    assert r.pontos == 15 and "proxy" in r.evidencia["criterio"]


def test_competicao_varios_fornecedores_nao_dispara(fazer_contrato):
    c = fazer_contrato(contratacao=_compra(6, 3), modalidade_id=6)
    assert CompeticaoBaixa(PESOS).avaliar(c, _ctx()) is None


def test_competicao_dispensa_nao_dispara(fazer_contrato):
    c = fazer_contrato(contratacao=_compra(8, 1), modalidade_id=8)
    assert CompeticaoBaixa(PESOS).avaliar(c, _ctx()) is None


def test_competicao_sem_dado_nao_dispara(fazer_contrato):
    assert CompeticaoBaixa(PESOS).avaliar(fazer_contrato(contratacao=_compra(6, None)), _ctx()) is None
    assert CompeticaoBaixa(PESOS).avaliar(fazer_contrato(), _ctx()) is None


def _com_aditivos(fazer_contrato, *valores):
    c = fazer_contrato(valor_inicial=Decimal("100000"), valor_global=Decimal("100000"))
    for i, v in enumerate(valores):
        c.aditivos.append(Aditivo(numero=str(i), valor_acrescimo=Decimal(v), data=date(2025, 6, 1),
                                  origem="pncp" if i == 0 else "diario"))
    db.session.commit()
    return c


def test_aditivo_30pct_dispara(fazer_contrato):
    c = _com_aditivos(fazer_contrato, "20000", "10000")
    r = AditivosExcessivos(PESOS).avaliar(c, _ctx())
    assert r.pontos == 20 and r.evidencia["percentual"] == 30.0
    assert [a["origem"] for a in r.evidencia["aditivos"]] == ["pncp", "diario"]


def test_aditivo_20pct_nao_dispara(fazer_contrato):
    assert AditivosExcessivos(PESOS).avaliar(_com_aditivos(fazer_contrato, "20000"), _ctx()) is None


def test_sem_aditivo_ou_valor_inicial_zero_nao_dispara(fazer_contrato):
    assert AditivosExcessivos(PESOS).avaliar(fazer_contrato(), _ctx()) is None
    c = fazer_contrato(valor_inicial=Decimal("0"), valor_global=Decimal("0"))
    c.aditivos.append(Aditivo(numero="1", valor_acrescimo=Decimal("5"), origem="pncp"))
    assert AditivosExcessivos(PESOS).avaliar(c, _ctx()) is None
