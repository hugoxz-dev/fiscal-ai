from datetime import date
from decimal import Decimal

from app.models import Contrato
from app.services.regras.base import Contexto
from app.services.regras.config import PESOS
from app.services.regras.dispensa import DispensaLimite
from app.services.regras.fracionamento import Fracionamento


def _ctx():
    return Contexto(contratos=Contrato.query.all(), sancoes={}, llm=None)


def test_dispensa_acima_limite_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("70000"), data_assinatura=date(2025, 5, 1),
                       objeto="Aquisição de material")
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r.codigo == "dispensa_limite" and r.pontos == 25
    assert r.evidencia["limite"] == "62725.59" and r.evidencia["categoria"] == "geral"
    assert r.evidencia["link"] == c.link_pncp


def test_dispensa_abaixo_limite_nao_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("60000"))
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is None


def test_dispensa_obra_abaixo_limite_obras_nao_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("100000"), objeto="Reforma de escola municipal")
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is None


def test_inexigibilidade_nao_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=9, valor_global=Decimal("900000"))
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is None


def test_ano_sem_tabela_usa_mais_recente(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("70000"), data_assinatura=date(2030, 1, 1))
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is not None


def test_fracionamento_tres_dispensas(fazer_contrato):
    cs = [fazer_contrato(modalidade_id=8, valor_global=Decimal("25000"), data_assinatura=date(2025, m, 1))
          for m in (2, 5, 9)]
    ctx = _ctx()
    regra = Fracionamento(PESOS)
    resultados = [regra.avaliar(c, ctx) for c in cs]
    assert all(r is not None and r.pontos == 20 for r in resultados)
    assert resultados[0].evidencia["soma"] == "75000.00"
    assert sorted(resultados[0].evidencia["contratos"]) == sorted(c.id for c in cs)


def test_fracionamento_anos_diferentes_nao_dispara(fazer_contrato):
    a = fazer_contrato(modalidade_id=8, valor_global=Decimal("40000"), data_assinatura=date(2024, 12, 1))
    b = fazer_contrato(modalidade_id=8, valor_global=Decimal("40000"), data_assinatura=date(2025, 1, 5))
    ctx = _ctx()
    assert Fracionamento(PESOS).avaliar(a, ctx) is None
    assert Fracionamento(PESOS).avaliar(b, ctx) is None


def test_fracionamento_ignora_dispensa_que_ja_passa_do_limite(fazer_contrato):
    grande = fazer_contrato(modalidade_id=8, valor_global=Decimal("70000"))
    fazer_contrato(modalidade_id=8, valor_global=Decimal("10000"))
    assert Fracionamento(PESOS).avaliar(grande, _ctx()) is None
