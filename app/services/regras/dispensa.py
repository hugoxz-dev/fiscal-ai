from __future__ import annotations

import re
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


_INCISO = re.compile(r"art\.?\s*75\s*,?\s*(?:inciso\s*)?([IVXL]+)\b", re.IGNORECASE)


def amparo_legal(contrato: Contrato) -> str | None:
    return contrato.contratacao.amparo_legal if contrato.contratacao else None


def dispensa_por_valor(contrato: Contrato) -> bool:
    """Dispensa do art. 75, I ou II (as únicas com teto de valor). Amparo desconhecido conta como sim."""
    if contrato.modalidade_id != MODALIDADE_DISPENSA:
        return False
    amparo = amparo_legal(contrato)
    if not amparo:
        return True
    m = _INCISO.search(amparo)
    return m is None or m.group(1).upper() in ("I", "II")


class DispensaLimite(Regra):
    codigo = "dispensa_limite"
    nome = "Dispensa acima do limite legal"
    base_legal = "Lei 14.133/2021, art. 75, I e II"
    descricao = ("Contratação por dispensa de valor (art. 75, I ou II) acima do limite permitido para a "
                 "categoria. Dispensas por outros motivos (emergência, por exemplo) não têm teto de valor.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not dispensa_por_valor(contrato) or contrato.valor_global is None:
            return None
        limite, categoria = limite_dispensa(contrato)
        if contrato.valor_global <= limite:
            return None
        return self.resultado(contrato, {"valor": fmt(contrato.valor_global), "limite": fmt(limite),
                                         "categoria": categoria, "amparo_legal": amparo_legal(contrato)})
