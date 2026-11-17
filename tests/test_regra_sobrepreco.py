from decimal import Decimal

from app.models import Contrato
from app.services.regras.base import Contexto
from app.services.regras.config import PESOS
from app.services.regras.sobrepreco import Sobrepreco

MERENDA = "Fornecimento de merenda escolar para as escolas da rede municipal"


def _avaliar_todos():
    ctx = Contexto(contratos=Contrato.query.all(), sancoes={}, llm=None)
    regra = Sobrepreco(PESOS)
    regra.preparar(ctx)
    return {c.id: regra.avaliar(c, ctx) for c in ctx.contratos}


def test_merenda_cara_dispara(fazer_contrato):
    normais = [fazer_contrato(objeto=MERENDA, valor_global=Decimal(v))
               for v in ("95000", "100000", "105000", "98000", "102000", "100000")]
    cara = fazer_contrato(objeto=MERENDA + " (lote 7)", valor_global=Decimal("350000"))
    res = _avaliar_todos()
    assert all(res[c.id] is None for c in normais)
    r = res[cara.id]
    assert r is not None and r.pontos == 20
    assert r.evidencia["mediana"] == "100000.00"
    assert r.evidencia["fator"] == 3.5
    assert r.evidencia["z_log"] > 0
    assert 1 <= len(r.evidencia["pares"]) <= 5 and {"id", "objeto", "valor"} <= set(r.evidencia["pares"][0])


def test_poucos_pares_nao_dispara(fazer_contrato):
    for v in ("95000", "100000", "105000", "98000"):
        fazer_contrato(objeto=MERENDA, valor_global=Decimal(v))
    cara = fazer_contrato(objeto=MERENDA, valor_global=Decimal("350000"))
    assert _avaliar_todos()[cara.id] is None


def test_objetos_diferentes_nao_sao_pares(fazer_contrato):
    for i in range(6):
        fazer_contrato(objeto=f"Locação de veículos tipo caminhonete lote {i}", valor_global=Decimal("100000"))
    cara = fazer_contrato(objeto="Aquisição de medicamentos hospitalares", valor_global=Decimal("900000"))
    assert _avaliar_todos()[cara.id] is None


def test_sem_preparar_nao_quebra(fazer_contrato, ctx_vazio):
    c = fazer_contrato(objeto=MERENDA)
    assert Sobrepreco(PESOS).avaliar(c, ctx_vazio) is None
