"""Normalização de texto e documentos usada na busca de políticos e nas ligações."""
from __future__ import annotations

import re
import unicodedata
import hashlib
from decimal import Decimal, InvalidOperation


def normalizar(s: str | None) -> str:
    """Sem acento, maiúsculo, espaços colapsados e sem pontas."""
    if not s:
        return ""
    sem = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(sem.upper().split())


def digitos(s: str | None) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def cpf_meio(doc: str | None) -> str | None:
    """Seis dígitos do meio do CPF (posições 4 a 9), de CPF completo ou mascarado (***682847**)."""
    doc = (doc or "").strip()
    if re.fullmatch(r"\d{11}", doc):
        return doc[3:9]
    m = re.fullmatch(r"\*{3}(\d{6})\*{2}", doc)
    return m.group(1) if m else None


def cpf_valido(s: str | None) -> str | None:
    d = (s or "").strip()
    return d if re.fullmatch(r"\d{11}", d) else None


def dinheiro_br(s) -> Decimal | None:
    """'893.200,00' -> Decimal; aceita float/int (Câmara)."""
    if s is None or isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return Decimal(str(s)).quantize(Decimal("0.01"))
    t = str(s).strip()
    if not t:
        return None
    try:
        return Decimal(t.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def codigo_despesa(cod, ano, mes, documento, numero) -> str:
    """Código do documento; se vier vazio, um código sintético estável (máx. 40 caracteres)."""
    cod = str(cod or "").strip()
    if cod and cod != "0":
        return cod[:40]
    bruto = f"s:{ano or 0}{int(mes or 0):02d}:{documento or ''}:{str(numero or '').strip()}"
    return bruto if len(bruto) <= 40 else "s:" + hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:38]
