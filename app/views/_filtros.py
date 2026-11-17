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


ROTULOS_EVIDENCIA = {
    "valor": "Valor do contrato", "limite": "Limite legal", "categoria": "Categoria", "soma": "Soma das dispensas",
    "ano": "Ano", "contratos": "Contratos somados (ids)", "valores": "Valores somados", "criterios": "Critérios",
    "data_abertura": "Abertura da empresa", "meses_entre_abertura_e_contrato": "Meses entre abertura e contrato",
    "capital_social": "Capital social", "valor_contrato": "Valor do contrato", "objeto": "Objeto",
    "cnae": "Atividade principal (CNAE)", "justificativa": "Justificativa do modelo", "modelo": "Modelo de linguagem",
    "sancoes": "Sanções vigentes", "percentual": "Percentual (%)", "total_orgao": "Total do órgão no ano",
    "total_fornecedor": "Total do fornecedor no ano", "contratos_orgao": "Contratos do órgão no ano",
    "criterio": "Critério", "contratacao": "Licitação", "modalidade": "Modalidade",
    "valor_inicial": "Valor inicial", "soma_acrescimos": "Soma dos acréscimos", "aditivos": "Aditivos",
    "mediana": "Mediana de contratos semelhantes", "fator": "Vezes a mediana", "z_log": "Desvio (z, escala log)",
    "qtd_pares": "Contratos semelhantes comparados", "pares": "Exemplos de contratos semelhantes",
}
CHAVES_DINHEIRO = {"valor", "limite", "soma", "capital_social", "valor_contrato", "total_orgao", "total_fornecedor",
                   "valor_inicial", "soma_acrescimos", "mediana"}


def evidencia_valor(chave: str, v):
    """Texto legível para um valor de evidência."""
    if chave in CHAVES_DINHEIRO and isinstance(v, str):
        try:
            return moeda(Decimal(v))
        except Exception:
            return v
    if isinstance(v, list):
        partes = []
        for item in v:
            if isinstance(item, dict):
                partes.append("; ".join(f"{k}: {moeda(Decimal(x)) if k == 'valor' else x}"
                                        for k, x in item.items() if x is not None))
            else:
                partes.append(str(item))
        return " | ".join(partes)
    return v


def registrar_filtros(app) -> None:
    app.jinja_env.filters.update(moeda=moeda, data_br=data_br, cnpj=cnpj, modalidade=modalidade,
                                 evidencia_valor=evidencia_valor)
    app.jinja_env.globals.update(ROTULOS_EVIDENCIA=ROTULOS_EVIDENCIA, evidencia_valor=evidencia_valor)
