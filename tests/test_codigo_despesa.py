from app.services.texto import codigo_despesa


def test_codigo_longo_fica_inteiro_e_vazio_vira_sintetico():
    longo = "980239B8-F7B1-4971-BB6C-A49FACCED137"
    assert codigo_despesa(longo, 2026, 3, "1", "A") == longo
    assert codigo_despesa("", 2026, 3, "12345678000199", "A1") == "s:202603:12345678000199:A1"
    gigante = codigo_despesa(None, 2026, 3, "12345678000199", "N" * 50)
    assert gigante.startswith("s:") and len(gigante) <= 40
    assert gigante == codigo_despesa(None, 2026, 3, "12345678000199", "N" * 50)


def test_codigo_zero_da_camara_conta_como_vazio():
    assert codigo_despesa("0", 2026, 3, "1", "A1") == "s:202603:1:A1"
    assert codigo_despesa(0, 2026, 3, "1", "A2") == "s:202603:1:A2"
