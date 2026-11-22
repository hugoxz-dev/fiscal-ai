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


def _com_amparo(fazer_contrato, amparo, **kw):
    from app.models import Contratacao

    c = fazer_contrato(**kw)
    c.contratacao = Contratacao(numero_controle_pncp=f"X-{c.id}", orgao=c.orgao, amparo_legal=amparo)
    db_commit()
    return c


def db_commit():
    from app.extensions import db

    db.session.commit()


def test_dispensa_emergencial_nao_tem_limite_de_valor(fazer_contrato, ctx_vazio):
    c = _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, VIII", modalidade_id=8, valor_global=Decimal("423070"))
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is None


def test_dispensa_por_valor_inciso_ii_dispara(fazer_contrato, ctx_vazio):
    c = _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, II", modalidade_id=8, valor_global=Decimal("70000"))
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r is not None and r.evidencia["amparo_legal"] == "Lei 14.133/2021, Art. 75, II"


def test_fracionamento_ignora_dispensa_sem_limite_de_valor(fazer_contrato):
    for _ in range(3):
        _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, VIII", modalidade_id=8, valor_global=Decimal("30000"))
    ctx = _ctx()
    assert all(Fracionamento(PESOS).avaliar(c, ctx) is None for c in ctx.contratos)


def test_dispensa_por_valor_reconhece_amparos():
    from types import SimpleNamespace as NS

    from app.services.regras.dispensa import dispensa_por_valor

    def c(amparo):
        return NS(modalidade_id=8, contratacao=NS(amparo_legal=amparo) if amparo is not None else None)

    assert dispensa_por_valor(c(None)) is True  # desconhecido: verifica
    assert dispensa_por_valor(c("Lei 14.133/2021, Art. 75, II")) is True
    assert dispensa_por_valor(c("Lei 14.133/2021, Art. 75, I")) is True
    assert dispensa_por_valor(c("Lei 8.666/1993, Art. 24, II")) is True
    for outro in ("Lei 14.133/2021, Art. 75, III", "Lei 14.133/2021, Art. 75, VIII", "Lei 14.133/2021, Art. 75, IV, a",
                  "Lei 8.666/1993, Art. 24, IV", "Lei 14.133/2021, Art. 75, § 7º"):
        assert dispensa_por_valor(c(outro)) is False, outro


def test_dispensa_2024_usa_limite_de_2024(fazer_contrato, ctx_vazio):
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("61000"), data_assinatura=date(2024, 6, 1))
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r is not None and r.evidencia["limite"] == "59906.02"


def test_dispensa_inciso_i_usa_limite_de_obras_mesmo_sem_palavra_chave(fazer_contrato, ctx_vazio):
    # Validação de 2026-11-22: manutenção com amparo no art. 75, I era comparada ao limite geral.
    c = _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, I", modalidade_id=8, valor_global=Decimal("124200"),
                    objeto="Manutenção preventiva e corretiva do sistema de climatização")
    assert DispensaLimite(PESOS).avaliar(c, ctx_vazio) is None


def test_dispensa_inciso_i_acima_do_limite_de_obras_dispara(fazer_contrato, ctx_vazio):
    c = _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, I", modalidade_id=8, valor_global=Decimal("130000"),
                    objeto="Manutenção de veículos")
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r is not None and r.evidencia["categoria"] == "obras" and r.evidencia["limite"] == "125451.15"


def test_dispensa_inciso_ii_usa_limite_geral_mesmo_com_palavra_de_obra(fazer_contrato, ctx_vazio):
    c = _com_amparo(fazer_contrato, "Lei 14.133/2021, Art. 75, II", modalidade_id=8, valor_global=Decimal("70000"),
                    objeto="Aquisição de material de construção")
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r is not None and r.evidencia["categoria"] == "geral"


def test_dispensa_2023_usa_limite_de_2023(fazer_contrato, ctx_vazio):
    # Decreto 11.317/2022: R$ 114.416,65 (I) e R$ 57.208,33 (II).
    c = fazer_contrato(modalidade_id=8, valor_global=Decimal("58000"), data_assinatura=date(2023, 6, 1))
    r = DispensaLimite(PESOS).avaliar(c, ctx_vazio)
    assert r is not None and r.evidencia["limite"] == "57208.33"


def test_fracionamento_objetos_de_naturezas_diferentes_nao_dispara(fazer_contrato):
    # Validação de 2026-11-22: a regra somava água mineral, brinquedos e algemas do mesmo fornecedor.
    for objeto in ("Fornecimento de água mineral", "Fornecimento de brinquedos novos e diversos",
                   "Aquisição de 250 unidades de algemas para a guarda municipal"):
        fazer_contrato(modalidade_id=8, valor_global=Decimal("25000"), objeto=objeto)
    ctx = _ctx()
    assert all(Fracionamento(PESOS).avaliar(c, ctx) is None for c in ctx.contratos)


def test_fracionamento_soma_so_os_objetos_semelhantes(fazer_contrato):
    a = fazer_contrato(modalidade_id=8, valor_global=Decimal("35000"), objeto="Fornecimento de material de expediente")
    b = fazer_contrato(modalidade_id=8, valor_global=Decimal("35000"), objeto="Fornecimento de material de expediente",
                       data_assinatura=date(2025, 8, 1))
    outro = fazer_contrato(modalidade_id=8, valor_global=Decimal("20000"), objeto="Serviço de dedetização predial")
    ctx = _ctx()
    r = Fracionamento(PESOS).avaliar(a, ctx)
    assert r is not None and sorted(r.evidencia["contratos"]) == sorted([a.id, b.id])
    assert Fracionamento(PESOS).avaliar(outro, ctx) is None


def test_fracionamento_nao_soma_contrato_publicado_em_duplicidade(fazer_contrato):
    # Validação de 2026-11-22: o mesmo contrato aparece duas vezes no PNCP (ids 829 e 1091).
    a = fazer_contrato(modalidade_id=8, valor_global=Decimal("40000"), objeto="Inspeção com drone do painel de azulejos")
    fazer_contrato(modalidade_id=8, valor_global=Decimal("40000"), objeto="Inspeção com drone do painel de azulejos.")
    assert Fracionamento(PESOS).avaliar(a, _ctx()) is None
