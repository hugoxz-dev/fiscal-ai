from datetime import date

import app.cli as cli


def test_coletar_pncp_repassa_periodo(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(cli, "FONTES", {"pncp": lambda de, ate, cfg: chamadas.append((de, ate)) or 7})
    result = app.test_cli_runner().invoke(args=["coletar", "--fonte", "pncp", "--de", "2025-01-01", "--ate", "2025-01-31"])
    assert result.exit_code == 0, result.output
    assert chamadas == [(date(2025, 1, 1), date(2025, 1, 31))]
    assert "pncp: 7 registros" in result.output


def test_coletar_fonte_invalida(app):
    result = app.test_cli_runner().invoke(args=["coletar", "--fonte", "xyz"])
    assert result.exit_code != 0
