import csv
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Alerta, Fornecedor
from app.services.validacao import (
    ErroValidacao,
    gravar_amostra,
    resumir,
    sortear_alertas,
    tabela_markdown,
)


@pytest.fixture
def alertas(fazer_contrato):
    """8 alertas de dispensa e 2 de sobrepreço."""
    for i in range(8):
        c = fazer_contrato(modalidade_id=8, valor_global=Decimal("70000"), objeto=f"Compra {i}",
                           link_pncp=f"https://pncp.gov.br/app/contratos/x/2025/{i}")
        db.session.add(Alerta(contrato=c, regra_codigo="dispensa_limite", pontos=25,
                              evidencia={"valor": "70000.00", "limite": "62725.59", "link": c.link_pncp}))
    pf = Fornecedor(documento="12345678901", nome="AGRICULTOR FULANO", tipo="PF")
    for i in range(2):
        c = fazer_contrato(fornecedor=pf, objeto=f"Serviço {i}")
        db.session.add(Alerta(contrato=c, regra_codigo="sobrepreco", pontos=20, evidencia={"fator": 3.1}))
    db.session.commit()


def _ler(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def test_amostra_limita_por_regra_e_e_reprodutivel(alertas):
    a1 = sortear_alertas(por_regra=5, semente=42)
    a2 = sortear_alertas(por_regra=5, semente=42)
    assert [a.id for a in a1] == [a.id for a in a2]
    por_regra = {}
    for a in a1:
        por_regra[a.regra_codigo] = por_regra.get(a.regra_codigo, 0) + 1
    assert por_regra == {"dispensa_limite": 5, "sobrepreco": 2}  # regra com poucos alertas entra inteira


def test_planilha_abre_no_excel_com_links_e_sem_cpf(alertas, tmp_path):
    caminho = tmp_path / "validacao.csv"
    gravar_amostra(caminho, sortear_alertas(por_regra=5, semente=1), "http://127.0.0.1:5000")
    bruto = caminho.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")  # BOM: Excel reconhece os acentos
    assert b"12345678901" not in bruto
    linhas = _ler(caminho)
    assert len(linhas) == 7
    dispensa = next(l for l in linhas if l["regra"] == "dispensa_limite")
    assert dispensa["nome_regra"] == "Dispensa acima do limite legal"
    assert dispensa["painel"].startswith("http://127.0.0.1:5000/contratos/")
    assert dispensa["fonte"].startswith("https://pncp.gov.br/")
    assert "Limite legal: R$ 62.725,59" in dispensa["evidencias"]
    assert dispensa["veredito"] == "" and "observacao" in dispensa
    sobre = next(l for l in linhas if l["regra"] == "sobrepreco")
    assert sobre["fornecedor"].startswith("AGRICULTOR FULANO (***.")


def _preencher(caminho, vereditos):
    linhas = _ler(caminho)
    for linha, v in zip(linhas, vereditos):
        linha["veredito"] = v
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)


def test_resumo_calcula_precisao_por_regra(alertas, tmp_path):
    caminho = tmp_path / "validacao.csv"
    gravar_amostra(caminho, sortear_alertas(por_regra=5, semente=1), "http://x")
    # 5 de dispensa (vêm primeiro, ordem por regra) e 2 de sobrepreço
    _preencher(caminho, ["acerto", "Acerto ", "falso positivo", "inconclusivo", "", "F", "a"])
    r = {x["regra"]: x for x in resumir(caminho)}
    d = r["dispensa_limite"]
    assert (d["avaliados"], d["acertos"], d["falsos"], d["inconclusivos"], d["pendentes"]) == (5, 2, 1, 1, 1)
    assert d["precisao"] == pytest.approx(2 / 3)
    s = r["sobrepreco"]
    assert (s["acertos"], s["falsos"]) == (1, 1) and s["precisao"] == pytest.approx(0.5)
    md = tabela_markdown(resumir(caminho))
    assert "| Dispensa acima do limite legal | 5 | 2 | 1 | 1 | 1 | 66,7% |" in md
    assert md.splitlines()[-1].startswith("| **Total** | 7 | 3 | 2 | 1 | 1 | 60,0% |")


def test_resumo_aponta_veredito_invalido_com_a_linha(alertas, tmp_path):
    caminho = tmp_path / "validacao.csv"
    gravar_amostra(caminho, sortear_alertas(por_regra=5, semente=1), "http://x")
    _preencher(caminho, ["acerto", "talvez"])
    with pytest.raises(ErroValidacao, match="linha 3.*talvez"):
        resumir(caminho)


def test_regra_sem_vereditos_tem_precisao_indefinida(alertas, tmp_path):
    caminho = tmp_path / "validacao.csv"
    gravar_amostra(caminho, sortear_alertas(por_regra=5, semente=1), "http://x")
    r = {x["regra"]: x for x in resumir(caminho)}
    assert r["sobrepreco"]["precisao"] is None
    assert "| Valor fora do padrão | 2 | 0 | 0 | 0 | 2 | — |" in tabela_markdown(resumir(caminho))


def test_comandos_cli(app, alertas, tmp_path):
    caminho = tmp_path / "v.csv"
    runner = app.test_cli_runner()
    r = runner.invoke(args=["validacao", "amostra", "--por-regra", "3", "--saida", str(caminho)])
    assert r.exit_code == 0, r.output
    assert "5 alertas" in r.output and caminho.exists()
    r = runner.invoke(args=["validacao", "resumo", str(caminho)])
    assert r.exit_code == 0, r.output
    assert "| Regra |" in r.output
    _preencher(caminho, ["xyz"])
    r = runner.invoke(args=["validacao", "resumo", str(caminho)])
    assert r.exit_code != 0 and "xyz" in r.output
