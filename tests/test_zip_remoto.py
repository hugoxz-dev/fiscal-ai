import io
import os
import zipfile

import pytest

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


class _Resp:
    def __init__(self, status, headers=None, content=b""):
        self.status_code, self.headers, self.content = status, headers or {}, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Sessao:
    def __init__(self, head, get=None):
        self._head, self._get = head, get

    def head(self, *a, **k):
        return self._head

    def get(self, *a, **k):
        return self._get


def test_abrir_membro_zip_inexistente_vira_keyerror(monkeypatch):
    from app.services.coletores import zip_remoto

    monkeypatch.setattr(zip_remoto, "criar_sessao", lambda: _Sessao(_Resp(404)))
    with pytest.raises(KeyError):
        zip_remoto.abrir_membro("https://x/y.zip", "a.csv")


def test_abrir_membro_falha_se_servidor_ignora_range(monkeypatch):
    from app.services.coletores import zip_remoto

    sessao = _Sessao(_Resp(200, {"Content-Length": "100"}), _Resp(200, content=b"x" * 100))
    monkeypatch.setattr(zip_remoto, "criar_sessao", lambda: sessao)
    with pytest.raises(RuntimeError, match="Range"):
        zip_remoto.abrir_membro("https://x/y.zip", "a.csv")
