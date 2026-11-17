"""Filtros Jinja para exibir valores no padrão brasileiro."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

MODALIDADES = {1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 4: "Concorrência eletrônica",
               5: "Concorrência presencial", 6: "Pregão eletrônico", 7: "Pregão presencial", 8: "Dispensa",
               9: "Inexigibilidade", 10: "Manifestação de interesse", 11: "Pré-qualificação",
               12: "Credenciamento", 13: "Leilão presencial"}


def moeda(v) -> str:
    if v is None:
        return "—"
    s = f"{Decimal(v):,.2f}"  # 1,234.50
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def cnpj(doc: str | None) -> str:
    d = "".join(c for c in (doc or "") if c.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    return doc or "—"


def modalidade(mid: int | None) -> str:
    return MODALIDADES.get(mid, "Não informada")


def registrar_filtros(app) -> None:
    app.jinja_env.filters.update(moeda=moeda, data_br=data_br, cnpj=cnpj, modalidade=modalidade)
