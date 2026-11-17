"""Parâmetros das regras de risco (ajustáveis e citados na página de Metodologia)."""
from decimal import Decimal

# Lei 14.133/2021, art. 75, I (obras/serviços de engenharia) e II (demais compras/serviços).
# 2024: Decreto 11.871/2023; 2025: Decreto 12.343/2024 — conferir o decreto vigente antes de cada ano.
LIMITES_DISPENSA = {
    2024: {"obras": Decimal("119812.02"), "geral": Decimal("59906.02")},
    2025: {"obras": Decimal("125451.15"), "geral": Decimal("62725.59")},
}

PESOS = {"dispensa_limite": 25, "fracionamento": 20, "fornecedor_novo": 20, "cnae": 10,
         "sancionado": 30, "concentracao": 15, "competicao": 15, "aditivos": 20, "sobrepreco": 20}

PARAMS = {"meses_fornecedor_novo": 6, "capital_min_pct": 0.10, "concentracao_pct": 0.30,
          "concentracao_min_contratos": 3, "aditivo_max_pct": 0.25, "sobrepreco_fator": 2.0,
          "sobrepreco_min_pares": 5, "sobrepreco_similaridade": 0.30}

NIVEIS = [(60, "Alto"), (30, "Médio"), (0, "Baixo")]

PALAVRAS_OBRAS = ["obra", "pavimenta", "constru", "reforma", "engenharia"]

MODALIDADE_DISPENSA = 8
MODALIDADE_INEXIGIBILIDADE = 9
