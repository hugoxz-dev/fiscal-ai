import json
from decimal import Decimal

import requests

from app.services import llm as llm_mod
from app.services.llm import OllamaClient


class RespostaFalsa:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _fake_post(texto_resposta, capturado=None):
    def post(url, json=None, timeout=None):
        if capturado is not None:
            capturado.append(json)
        return RespostaFalsa({"response": texto_resposta})
    return post


def cliente():
    return OllamaClient("http://localhost:11434", "qwen2.5:7b")


def test_json_invalido_retorna_none(monkeypatch):
    monkeypatch.setattr(llm_mod.requests, "post", _fake_post("não é json"))
    assert cliente().gerar_json("x") is None


def test_conexao_recusada_retorna_none(monkeypatch):
    def recusa(*a, **k):
        raise requests.ConnectionError("recusada")
    monkeypatch.setattr(llm_mod.requests, "post", recusa)
    monkeypatch.setattr(llm_mod.requests, "get", recusa)
    c = cliente()
    assert c.gerar_json("x") is None
    assert c.disponivel() is False
    assert c.explicar({"objeto": "x"}, [{"regra": "y"}]) is None


def test_gerar_json_envia_formato_e_temperatura_zero(monkeypatch):
    enviado = []
    monkeypatch.setattr(llm_mod.requests, "post", _fake_post('{"a": 1}', enviado))
    assert cliente().gerar_json("p") == {"a": 1}
    assert enviado[0]["format"] == "json" and enviado[0]["stream"] is False
    assert enviado[0]["options"]["temperature"] == 0 and enviado[0]["model"] == "qwen2.5:7b"


def test_extrair_normaliza(monkeypatch):
    resposta = json.dumps({"tipo": "Dispensa", "documento_fornecedor": "12.345.678/0001-99",
                           "valor": "R$ 10.500,00", "objeto": "x"})
    monkeypatch.setattr(llm_mod.requests, "post", _fake_post(resposta))
    r = cliente().extrair_extrato("trecho")
    assert r == {"tipo": "dispensa", "documento_fornecedor": "12345678000199",
                 "valor": Decimal("10500.00"), "objeto": "x"}


def test_extrair_tipo_desconhecido_vira_outro(monkeypatch):
    resposta = json.dumps({"tipo": "portaria", "documento_fornecedor": None, "valor": None, "objeto": None})
    monkeypatch.setattr(llm_mod.requests, "post", _fake_post(resposta))
    assert cliente().extrair_extrato("t")["tipo"] == "outro"


def test_cnae_compativel(monkeypatch):
    monkeypatch.setattr(llm_mod.requests, "post",
                        _fake_post('{"compativel": false, "justificativa": "atividades distintas"}'))
    assert cliente().cnae_compativel("obra de ponte", "Produção musical") == (False, "atividades distintas")


def test_explicar_prompt_proibe_acusacao(monkeypatch):
    enviado = []
    monkeypatch.setattr(llm_mod.requests, "post", _fake_post('{"texto": "Foram observados indícios."}', enviado))
    texto = cliente().explicar({"objeto": "merenda"}, [{"regra": "Aditivos", "evidencia": {"pct": 0.3}}])
    assert texto == "Foram observados indícios."
    assert "Não afirme que houve fraude ou crime" in enviado[0]["prompt"]
