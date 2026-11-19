from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Alerta, Contrato, Fornecedor, Sancao
from app.services import analisador
from app.services.analisador import REGRAS, analisar_todos, explicar_pendentes, nivel_para


@pytest.fixture
def cenario(fazer_contrato):
    nova = Fornecedor(documento="11222333000144", nome="NOVA LTDA", tipo="PJ",
                      data_abertura=date(2025, 3, 1), capital_social=Decimal("1000"))
    db.session.add(Sancao(documento="11222333000144", cadastro="CEIS", data_inicio=date(2024, 1, 1)))
    ruim = fazer_contrato(fornecedor=nova, modalidade_id=8, valor_global=Decimal("90000"),
                          data_assinatura=date(2025, 5, 1))
    limpo = fazer_contrato(valor_global=Decimal("5000"))
    fazer_contrato(valor_global=Decimal("6000"))
    fazer_contrato(valor_global=Decimal("7000"))
    return ruim, limpo


class LLMFalso:
    model = "falso"

    def __init__(self, texto="Texto explicativo."):
        self.texto, self.chamadas = texto, 0

    def cnae_compativel(self, objeto, cnae):
        return None

    def explicar(self, resumo, alertas):
        self.chamadas += 1
        return self.texto


def test_regras_registradas():
    assert [r.codigo for r in REGRAS] == ["dispensa_limite", "fracionamento", "fornecedor_novo", "cnae",
                                          "sancionado", "concentracao", "competicao", "aditivos", "sobrepreco"]


def test_niveis():
    assert nivel_para(60) == "Alto" and nivel_para(59) == "Médio"
    assert nivel_para(30) == "Médio" and nivel_para(29) == "Baixo" and nivel_para(0) == "Baixo"


def test_analise_pontua_contrato_ruim(app, cenario):
    ruim, limpo = cenario
    resumo = analisar_todos(None)
    # dispensa acima do limite (25) + fornecedor novo (20) + sancionado (30) + concentração (15) = 90
    assert ruim.score == 90 and ruim.nivel == "Alto"
    assert {a.regra_codigo for a in ruim.alertas} == {"dispensa_limite", "fornecedor_novo", "sancionado",
                                                     "concentracao"}
    assert limpo.score == 0 and limpo.nivel == "Baixo" and limpo.analisado_em is not None
    assert resumo["contratos"] == 4 and resumo["alto"] == 1


def test_score_limitado_a_100(app, cenario, monkeypatch):
    from app.services.regras.config import PESOS
    monkeypatch.setitem(PESOS, "sancionado", 90)
    ruim, _ = cenario
    analisar_todos(None)
    assert ruim.score == 100


def test_reanalise_idempotente(app, cenario):
    analisar_todos(None)
    s1 = [(c.id, c.score) for c in Contrato.query.order_by(Contrato.id)]
    n1 = Alerta.query.count()
    analisar_todos(None)
    assert [(c.id, c.score) for c in Contrato.query.order_by(Contrato.id)] == s1
    assert Alerta.query.count() == n1


def test_explicar_pendentes(app, cenario):
    ruim, limpo = cenario
    analisar_todos(None)
    llm = LLMFalso()
    assert explicar_pendentes(llm, limite=10) == 1
    assert ruim.explicacao == "Texto explicativo." and limpo.explicacao is None
    assert explicar_pendentes(llm, limite=10) == 0 and llm.chamadas == 1


def test_explicar_llm_indisponivel_nao_quebra(app, cenario):
    ruim, _ = cenario
    analisar_todos(None)
    assert explicar_pendentes(LLMFalso(texto=None), limite=10) == 0
    assert ruim.explicacao is None


def test_reanalise_com_score_alterado_limpa_explicacao(app, cenario):
    ruim, _ = cenario
    analisar_todos(None)
    explicar_pendentes(LLMFalso(), limite=10)
    db.session.delete(Sancao.query.one())
    db.session.commit()
    analisar_todos(None)
    assert ruim.score == 60 and ruim.explicacao is None


def test_cli_analisar_sem_ollama(app, cenario, monkeypatch):
    class Indisponivel:
        def disponivel(self):
            return False
    monkeypatch.setattr(analisador, "get_llm", lambda: Indisponivel())
    out = app.test_cli_runner().invoke(args=["analisar"]).output
    assert "Ollama indisponível — regra de CNAE usa só os julgamentos já guardados" in out
    assert "Alto: 1" in out
