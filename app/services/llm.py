"""Cliente do Ollama (LLM local).

O LLM NÃO decide se um contrato é suspeito. Ele só:
  (a) extrai campos estruturados de textos do Diário Oficial,
  (b) julga a compatibilidade entre objeto e CNAE (regra de peso menor),
  (c) redige em português a explicação de indícios já calculados pelas regras.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

import requests
from flask import current_app

TIPOS_EXTRATO = {"contrato", "dispensa", "inexigibilidade", "aditivo", "outro"}

PROMPT_EXTRATO = """Você lê trechos do Diário Oficial do Município de São Luís/MA.
Extraia os dados do trecho abaixo e responda SOMENTE com JSON no formato:
{{"tipo": "contrato|dispensa|inexigibilidade|aditivo|outro",
  "documento_fornecedor": "CNPJ ou CPF do contratado, ou null",
  "nome_fornecedor": "razão social ou nome do contratado, ou null",
  "valor": "valor total em reais, ou null",
  "objeto": "objeto resumido em uma frase, ou null"}}
Não invente dados: use null quando a informação não estiver no trecho.

TRECHO:
{trecho}"""

PROMPT_CNAE = """Um órgão público contratou uma empresa para o objeto abaixo.
As atividades econômicas (CNAE principal e secundárias) da empresa são informadas a seguir.
Responda SOMENTE com JSON: {{"compativel": true ou false, "justificativa": "uma frase"}}
Considere compatível se QUALQUER uma das atividades razoavelmente inclui fornecer esse objeto.
Quem fabrica, comercializa (atacado ou varejo) ou distribui um bem pode fornecê-lo.
Só responda false quando nenhuma atividade tiver relação com o objeto.

OBJETO: {objeto}
ATIVIDADES:
{cnae}"""

PROMPT_EXPLICAR = """Você é um assistente de controle social de gastos públicos.
Escreva em português do Brasil um texto de 3 a 6 frases explicando, para um cidadão comum,
por que o contrato abaixo recebeu alertas de risco. Use somente os fatos fornecidos.
Não afirme que houve fraude ou crime; descreva apenas os indícios a partir dos dados fornecidos.
Responda SOMENTE com JSON: {{"texto": "..."}}

CONTRATO:
{contrato}

INDÍCIOS CALCULADOS PELAS REGRAS:
{alertas}"""


def _so_digitos(v) -> str | None:
    d = "".join(c for c in str(v or "") if c.isdigit())
    return d if len(d) in (11, 14) else None


def _valor(v) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(v)).quantize(Decimal("0.01"))
    s = re.sub(r"[^\d,.]", "", str(v))
    if "," in s:  # formato brasileiro 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def disponivel(self) -> bool:
        try:
            requests.get(f"{self.base_url}/api/tags", timeout=5).raise_for_status()
            return True
        except requests.RequestException:
            return False

    def gerar_json(self, prompt: str) -> dict | None:
        corpo = {"model": self.model, "prompt": prompt, "format": "json", "stream": False,
                 "options": {"temperature": 0}}
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=corpo, timeout=self.timeout)
            resp.raise_for_status()
            dados = json.loads(resp.json().get("response", ""))
        except (requests.RequestException, ValueError):
            return None
        return dados if isinstance(dados, dict) else None

    def extrair_extrato(self, trecho: str) -> dict | None:
        d = self.gerar_json(PROMPT_EXTRATO.format(trecho=trecho[:6000]))
        if d is None:
            return None
        tipo = str(d.get("tipo") or "").strip().lower()
        return {
            "tipo": tipo if tipo in TIPOS_EXTRATO else "outro",
            "documento_fornecedor": _so_digitos(d.get("documento_fornecedor")),
            "nome_fornecedor": (str(d.get("nome_fornecedor") or "").strip() or None),
            "valor": _valor(d.get("valor")),
            "objeto": d.get("objeto") or None,
        }

    def cnae_compativel(self, objeto: str, cnae_descricao: str) -> tuple[bool, str] | None:
        d = self.gerar_json(PROMPT_CNAE.format(objeto=objeto, cnae=cnae_descricao))
        if d is None or not isinstance(d.get("compativel"), bool):
            return None
        return d["compativel"], str(d.get("justificativa") or "")

    def explicar(self, contrato_resumo: dict, alertas: list[dict]) -> str | None:
        prompt = PROMPT_EXPLICAR.format(
            contrato=json.dumps(contrato_resumo, ensure_ascii=False, default=str, indent=1),
            alertas=json.dumps(alertas, ensure_ascii=False, default=str, indent=1),
        )
        d = self.gerar_json(prompt)
        texto = (d or {}).get("texto")
        return texto.strip() if isinstance(texto, str) and texto.strip() else None


def get_llm() -> OllamaClient:
    cfg = current_app.config
    return OllamaClient(cfg["OLLAMA_URL"], cfg["OLLAMA_MODEL"])
