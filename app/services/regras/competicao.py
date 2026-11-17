from __future__ import annotations

from ...models import Contrato
from .base import Contexto, Regra, Resultado
from .config import MODALIDADE_DISPENSA, MODALIDADE_INEXIGIBILIDADE


class CompeticaoBaixa(Regra):
    codigo = "competicao"
    nome = "Baixa competição na licitação"
    base_legal = "Lei 14.133/2021, art. 5º e art. 11 (competição e proposta mais vantajosa)"
    descricao = ("Licitação com vários itens em que um único fornecedor venceu todos. O PNCP não informa o "
                 "número de participantes, então este indicador é uma aproximação (proxy).")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        compra = contrato.contratacao
        if compra is None or compra.modalidade_id in (MODALIDADE_DISPENSA, MODALIDADE_INEXIGIBILIDADE):
            return None
        if compra.qtd_fornecedores_resultado != 1:
            return None
        return self.resultado(contrato, {
            "criterio": "proxy: um único fornecedor nos resultados dos itens",
            "contratacao": compra.numero_controle_pncp,
            "modalidade": compra.modalidade_nome or compra.modalidade_id,
            "link_contratacao": compra.link_pncp,
        })
