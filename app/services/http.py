"""Sessão HTTP compartilhada pelos coletores (retry com backoff)."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT_PADRAO = 120  # o PNCP chega a levar >60 s em consultas filtradas


def criar_sessao(headers: dict | None = None) -> requests.Session:
    sessao = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET", "POST"])
    sessao.mount("https://", HTTPAdapter(max_retries=retry))
    sessao.mount("http://", HTTPAdapter(max_retries=retry))
    sessao.headers.update({"Accept": "application/json", "User-Agent": "FiscalAI-TCC/1.0"})
    if headers:
        sessao.headers.update(headers)
    return sessao


def get_json(sessao: requests.Session, url: str, params: dict | None = None,
             timeout: int = TIMEOUT_PADRAO):
    """GET que devolve o JSON, ou None quando não há conteúdo (204/404)."""
    resp = sessao.get(url, params=params, timeout=timeout)
    if resp.status_code in (204, 404):
        return None
    resp.raise_for_status()
    if not resp.content:
        return None
    return resp.json()
