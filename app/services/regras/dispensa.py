from __future__ import annotations

from decimal import Decimal

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import LIMITES_DISPENSA, MODALIDADE_DISPENSA, PALAVRAS_OBRAS


def limite_dispensa(contrato: Contrato) -> tuple[Decimal, str]:
    """Limite de dispensa (art. 75) aplicável ao contrato e a categoria usada."""
    ano = contrato.data_assinatura.year if contrato.data_assinatura else max(LIMITES_DISPENSA)
    tabela = LIMITES_DISPENSA.get(ano) or LIMITES_DISPENSA[max(LIMITES_DISPENSA)]
    objeto = (contrato.objeto or "").lower()
    categoria = "obras" if any(p in objeto for p in PALAVRAS_OBRAS) else "geral"
    return tabela[categoria], categoria


class DispensaLimite(Regra):
    codigo = "dispensa_limite"
    nome = "Dispensa acima do limite legal"
    base_legal = "Lei 14.133/2021, art. 75, I e II"
    descricao = "Contratação por dispensa de licitação com valor acima do limite permitido para a categoria."

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if contrato.modalidade_id != MODALIDADE_DISPENSA or contrato.valor_global is None:
            return None
        limite, categoria = limite_dispensa(contrato)
        if contrato.valor_global <= limite:
            return None
        return self.resultado(contrato, {"valor": fmt(contrato.valor_global), "limite": fmt(limite),
                                         "categoria": categoria})
