from __future__ import annotations

from datetime import date
from decimal import Decimal

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS


def meses_entre(inicio: date, fim: date) -> int:
    meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    return meses - 1 if fim.day < inicio.day else meses


class FornecedorNovo(Regra):
    codigo = "fornecedor_novo"
    nome = "Fornecedor recém-criado ou com capital baixo"
    base_legal = "Lei 14.133/2021, art. 69 (qualificação econômico-financeira); metodologia CGU/TCU"
    descricao = (f"Empresa aberta menos de {PARAMS['meses_fornecedor_novo']} meses antes do contrato, ou com "
                 f"capital social inferior a {int(PARAMS['capital_min_pct'] * 100)}% do valor contratado.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        f = contrato.fornecedor
        if f is None or f.tipo != "PJ":
            return None
        criterios, evidencia = [], {}
        if f.data_abertura and contrato.data_assinatura:
            meses = meses_entre(f.data_abertura, contrato.data_assinatura)
            if meses < PARAMS["meses_fornecedor_novo"]:
                criterios.append("empresa_recente")
                evidencia.update({"data_abertura": f.data_abertura.isoformat(),
                                  "meses_entre_abertura_e_contrato": meses})
        if f.capital_social is not None and contrato.valor_global:
            minimo = contrato.valor_global * Decimal(str(PARAMS["capital_min_pct"]))
            if f.capital_social < minimo:
                criterios.append("capital_baixo")
                evidencia.update({"capital_social": fmt(f.capital_social), "valor_contrato": fmt(contrato.valor_global)})
        if not criterios:
            return None
        return self.resultado(contrato, {"criterios": criterios, **evidencia})
