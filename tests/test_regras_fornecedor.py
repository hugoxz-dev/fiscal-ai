from datetime import date
from decimal import Decimal

from app.models import Fornecedor, Sancao
from app.services.regras.base import Contexto
from app.services.regras.cnae import CnaeIncompativel
from app.services.regras.config import PESOS
from app.services.regras.fornecedor_novo import FornecedorNovo
from app.services.regras.sancionado import Sancionado


def _pj(**kw):
    dados = dict(documento="11222333000144", nome="NOVA LTDA", tipo="PJ", data_abertura=date(2020, 1, 1),
                 capital_social=Decimal("1000000.00"), cnae_descricao="Comércio varejista de material de escritório")
    dados.update(kw)
    return Fornecedor(**dados)


class LLMFalso:
    def __init__(self, resposta):
        self.resposta, self.model = resposta, "qwen2.5:7b"

    def cnae_compativel(self, objeto, cnae):
        return self.resposta


def test_aberta_3_meses_antes_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(fornecedor=_pj(data_abertura=date(2025, 2, 1)), data_assinatura=date(2025, 5, 1))
    r = FornecedorNovo(PESOS).avaliar(c, ctx_vazio)
    assert r.pontos == 20 and r.evidencia["criterios"] == ["empresa_recente"]
    assert r.evidencia["meses_entre_abertura_e_contrato"] == 3


def test_capital_baixo_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(fornecedor=_pj(capital_social=Decimal("5000")), valor_global=Decimal("100000"))
    r = FornecedorNovo(PESOS).avaliar(c, ctx_vazio)
    assert r.evidencia["criterios"] == ["capital_baixo"]
    assert r.evidencia["capital_social"] == "5000.00"


def test_empresa_antiga_e_capitalizada_nao_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(fornecedor=_pj())
    assert FornecedorNovo(PESOS).avaliar(c, ctx_vazio) is None


def test_pf_sem_dados_nao_dispara(fazer_contrato, ctx_vazio):
    pf = Fornecedor(documento="12345678901", nome="FULANO", tipo="PF")
    c = fazer_contrato(fornecedor=pf)
    assert FornecedorNovo(PESOS).avaliar(c, ctx_vazio) is None
    assert Sancionado(PESOS).avaliar(c, ctx_vazio) is None
    assert CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, LLMFalso((False, "x")))) is None


def test_cnae_sem_llm_nao_dispara(fazer_contrato, ctx_vazio):
    c = fazer_contrato(fornecedor=_pj())
    assert CnaeIncompativel(PESOS).avaliar(c, ctx_vazio) is None


def test_cnae_llm_none_nao_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj())
    assert CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, LLMFalso(None))) is None


def test_cnae_incompativel_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), objeto="Pavimentação asfáltica")
    r = CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, LLMFalso((False, "papelaria não faz asfalto"))))
    assert r.pontos == 10
    assert r.evidencia["justificativa"] == "papelaria não faz asfalto" and r.evidencia["modelo"] == "qwen2.5:7b"


def test_cnae_compativel_nao_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj())
    assert CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, LLMFalso((True, "ok")))) is None


def _sancao(inicio, fim):
    return Sancao(documento="11222333000144", cadastro="CEIS", data_inicio=inicio, data_fim=fim,
                  orgao_sancionador="TCE-MA", descricao="Impedimento")


def test_sancao_vigente_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), data_assinatura=date(2025, 5, 1))
    ctx = Contexto([], {"11222333000144": [_sancao(date(2024, 1, 1), date(2026, 1, 1))]}, None)
    r = Sancionado(PESOS).avaliar(c, ctx)
    assert r.pontos == 30 and r.evidencia["sancoes"][0]["cadastro"] == "CEIS"


def test_sancao_sem_data_fim_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), data_assinatura=date(2025, 5, 1))
    ctx = Contexto([], {"11222333000144": [_sancao(date(2024, 1, 1), None)]}, None)
    assert Sancionado(PESOS).avaliar(c, ctx) is not None


def test_sancao_expirada_nao_dispara(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), data_assinatura=date(2025, 5, 1))
    ctx = Contexto([], {"11222333000144": [_sancao(date(2022, 1, 1), date(2023, 1, 1))]}, None)
    assert Sancionado(PESOS).avaliar(c, ctx) is None


class LLMContador(LLMFalso):
    def __init__(self, resposta):
        super().__init__(resposta)
        self.chamadas = 0

    def cnae_compativel(self, objeto, cnae):
        self.chamadas += 1
        return self.resposta


def test_cnae_julgamento_fica_guardado_e_nao_repete(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), objeto="Pavimentação asfáltica")
    llm = LLMContador((False, "papelaria não faz asfalto"))
    r1 = CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    r2 = CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    assert llm.chamadas == 1
    assert r1.evidencia == r2.evidencia


def test_cnae_julgamento_refeito_se_cnae_mudar(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj(), objeto="Pavimentação asfáltica")
    llm = LLMContador((True, "ok"))
    CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    c.fornecedor.cnae_descricao = "Construção de rodovias"
    CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    assert llm.chamadas == 2


def test_cnae_resposta_none_nao_e_guardada(fazer_contrato):
    c = fazer_contrato(fornecedor=_pj())
    llm = LLMContador(None)
    CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    CnaeIncompativel(PESOS).avaliar(c, Contexto([], {}, llm))
    assert llm.chamadas == 2


def test_capital_zero_e_tratado_como_nao_informado(fazer_contrato, ctx_vazio):
    # Associações e cooperativas não têm capital social: a Receita devolve 0.
    c = fazer_contrato(fornecedor=_pj(capital_social=Decimal("0.00")), valor_global=Decimal("100000"))
    assert FornecedorNovo(PESOS).avaliar(c, ctx_vazio) is None
