import io
import os
import zipfile

from app.services.coletores.zip_remoto import LeitorIntervalo


def test_leitor_intervalo_le_membro_de_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a_MA.csv", "ação;1\n" * 10)
        z.writestr("b.csv", os.urandom(200000))
    dados = buf.getvalue()
    chamadas = []

    def baixar(i, f):
        chamadas.append((i, f))
        return dados[i:f + 1]

    leitor = io.BufferedReader(LeitorIntervalo(len(dados), baixar), 4096)
    with zipfile.ZipFile(leitor) as z:
        assert z.read("a_MA.csv").decode() == "ação;1\n" * 10
    assert 0 < len(chamadas) < 20
    assert sum(f - i + 1 for i, f in chamadas) < len(dados) // 4
