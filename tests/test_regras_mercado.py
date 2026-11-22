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


# Validação de 2026-11-22: a Prefeitura informa no campo "valor acrescido" o novo valor global do contrato.
def _termo(numero, acrescimo, valor_global, dia):
    return Aditivo(numero=numero, valor_acrescimo=Decimal(acrescimo), valor_global=Decimal(valor_global),
                   data=date(2025, 6, dia), origem="pncp")


def _contrato_com_termos(fazer_contrato, inicial, *termos):
    c = fazer_contrato(valor_inicial=Decimal(inicial), valor_global=Decimal(inicial))
    c.aditivos.extend(termos)
    db.session.commit()
    return c


def test_acrescimo_informado_como_novo_valor_global_usa_a_diferenca(fazer_contrato):
    c = _contrato_com_termos(fazer_contrato, "32400", _termo("1", "40500", "40500", 1))
    assert AditivosExcessivos(PESOS).avaliar(c, _ctx()) is None  # 8.100 = 25%


def test_novo_valor_global_menor_e_supressao_e_nao_conta(fazer_contrato):
    c = _contrato_com_termos(fazer_contrato, "14125846.01", _termo("1", "12963117.65", "12963117.65", 1))
    assert AditivosExcessivos(PESOS).avaliar(c, _ctx()) is None


def test_diferenca_parte_do_valor_apos_o_termo_anterior(fazer_contrato):
    c = _contrato_com_termos(fazer_contrato, "1000", _termo("1", "1100", "1100", 1), _termo("2", "1400", "1400", 2))
    r = AditivosExcessivos(PESOS).avaliar(c, _ctx())
    assert r is not None and r.evidencia["percentual"] == 40.0
    assert [a["valor"] for a in r.evidencia["aditivos"]] == ["100.00", "300.00"]


def test_acrescimo_coerente_com_valor_global_conta_inteiro(fazer_contrato):
    c = _contrato_com_termos(fazer_contrato, "1000", _termo("1", "500", "1500", 1))
    r = AditivosExcessivos(PESOS).avaliar(c, _ctx())
    assert r is not None and r.evidencia["percentual"] == 50.0


# Validação de 2026-11-22: anos com coleta parcial, duplicatas e valor digitado errado distorciam o percentual.
def test_concentracao_ignora_ano_com_coleta_parcial(fazer_contrato):
    for i in range(10):
        fazer_contrato(fornecedor=_forn(f"{i:02d}000000000100"), valor_global=Decimal("1000"))
    alvo = fazer_contrato(fornecedor=_forn("11111111000111"), valor_global=Decimal("90000"),
                          data_assinatura=date(2023, 5, 1))
    for doc in ("22222222000122", "33333333000133"):
        fazer_contrato(fornecedor=_forn(doc), valor_global=Decimal("5000"), data_assinatura=date(2023, 6, 1))
    assert Concentracao(PESOS).avaliar(alvo, _ctx()) is None


def test_concentracao_conta_contrato_duplicado_uma_vez(fazer_contrato):
    a = _forn("11111111000111")
    alvo = fazer_contrato(fornecedor=a, valor_global=Decimal("30000"), objeto="Serviço de limpeza.")
    fazer_contrato(fornecedor=a, valor_global=Decimal("30000"), objeto="Serviço de limpeza")
    fazer_contrato(fornecedor=_forn("22222222000122"), valor_global=Decimal("35000"))
    fazer_contrato(fornecedor=_forn("33333333000133"), valor_global=Decimal("35000"))
    assert Concentracao(PESOS).avaliar(alvo, _ctx()) is None  # 30 mil de 100 mil = 30%


def test_concentracao_ignora_valor_mil_vezes_maior_para_o_mesmo_objeto(fazer_contrato):
    a = _forn("11111111000111")
    certo = fazer_contrato(fornecedor=a, valor_global=Decimal("1500000"), objeto="Locação do imóvel da CPL")
    errado = fazer_contrato(fornecedor=a, valor_global=Decimal("1500000000"), objeto="Locação do imóvel da CPL",
                            data_assinatura=date(2025, 11, 6))
    for doc in ("22222222000122", "33333333000133", "44444444000144"):
        fazer_contrato(fornecedor=_forn(doc), valor_global=Decimal("10000000"))
    ctx = _ctx()
    assert Concentracao(PESOS).avaliar(certo, ctx) is None
    assert Concentracao(PESOS).avaliar(errado, ctx) is None


def test_valor_muito_maior_mas_nao_potencia_de_10_nao_e_erro_de_digitacao(fazer_contrato):
    # Duas compras da mesma ata de luvas (R$ 3,2 milhões e R$ 20 mil): quantidades diferentes, não erro.
    from app.services.regras.qualidade import valores_suspeitos

    a = _forn("11111111000111")
    fazer_contrato(fornecedor=a, valor_global=Decimal("3249300.00"), objeto="Registro de preço de luvas")
    fazer_contrato(fornecedor=a, valor_global=Decimal("20062.08"), objeto="Registro de preço de luvas")
    assert valores_suspeitos(_ctx()) == set()


def test_termo_de_prazo_com_valor_original_nao_reinicia_a_conta(fazer_contrato):
    # Contrato 747: o termo de prazo informa o valor original como valor global, mesmo após um acréscimo.
    c = _contrato_com_termos(fazer_contrato, "1000", _termo("1", "1180", "1180", 1), _termo("2", "0", "1000", 2),
                             _termo("3", "1260", "1260", 3))
    r = AditivosExcessivos(PESOS).avaliar(c, _ctx())
    assert r is not None and r.evidencia["percentual"] == 26.0
    assert [a["valor"] for a in r.evidencia["aditivos"]] == ["180.00", "0.00", "80.00"]


# Os termos do PNCP costumam declarar o percentual no texto; ele vale mais que a conta pelo valor global,
# que mistura prorrogação e reajuste (contratos 524 e 728 da validação de 2026-11-22).
def test_percentual_declarado_de_acrescimo():
    from app.services.regras.aditivos import percentual_acrescimo_declarado as pct

    assert pct("Acréscimo nos itens 02 e 03 - 2,99%") == Decimal("2.99")
    assert pct("tem como objeto o acréscimo quantitativo e qualitativo (22,44%) e supressão (1,35%) do objeto") \
        == Decimal("22.44")
    assert pct("em decorrência do acréscimo quantitativo e qualitativo de R$535.335,96, correspondente a 8,93%, e "
               "em decorrência da supressão quantitativa de R$ 95.075,55, correspondente a 1,59% do valor") \
        == Decimal("8.93")
    assert pct("Prorrogação do prazo de vigência por 12 meses") is None
    assert pct("Supressão de 10% do objeto") is None
    assert pct("Reajuste de 4,5% pelo IPCA") is None
    assert pct(None) is None


def _termo_texto(numero, acrescimo, valor_global, dia, descricao):
    t = _termo(numero, acrescimo, valor_global, dia)
    t.descricao = descricao
    return t


def test_percentual_declarado_substitui_a_conta_pelo_valor(fazer_contrato):
    c = _contrato_com_termos(fazer_contrato, "6039720",
                             _termo_texto("3", "7585363.08", "7585363.08", 1, "Acréscimo nos itens 02 e 03 - 2,99%"))
    assert AditivosExcessivos(PESOS).avaliar(c, _ctx()) is None


def test_soma_percentual_declarado_com_conta_pelo_valor_dos_termos_sem_texto(fazer_contrato):
    # Contrato 747: termo 1 sem percentual (18,0% pelo valor) + termo 3 declarando 8,93%.
    c = _contrato_com_termos(fazer_contrato, "1000", _termo("1", "1180", "1180", 1),
                             _termo_texto("3", "1260", "1260", 3, "acréscimo quantitativo de 8,93% e supressão de 1,59%"))
    r = AditivosExcessivos(PESOS).avaliar(c, _ctx())
    assert r is not None and r.evidencia["percentual"] == 26.9
    assert [a["valor"] for a in r.evidencia["aditivos"]] == ["180.00", "89.30"]
    assert [a["criterio"] for a in r.evidencia["aditivos"]] == ["valor global", "percentual declarado"]


def test_percentual_repetido_no_mesmo_texto_conta_uma_vez():
    # Termo 004/2026 do contrato 728: cita 22,44% no objeto e de novo na cláusula de valor.
    from app.services.regras.aditivos import percentual_acrescimo_declarado as pct

    texto = ("tem como objeto o acréscimo quantitativo e qualitativo (22,44%) e supressão (1,35%) do objeto. "
             "Fica alterada a cláusula quinta, em decorrência do acréscimo quantitativo e qualitativo de "
             "R$612.388,01, correspondente a 22,44%, e da supressão de R$ 36.813,42, correspondente a 1,35%")
    assert pct(texto) == Decimal("22.44")
