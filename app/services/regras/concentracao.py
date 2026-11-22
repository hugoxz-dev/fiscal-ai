from __future__ import annotations

from ...models import Contrato
from .base import Contexto, Regra, Resultado, fmt
from .config import PARAMS
from .qualidade import anos_cobertos, sem_duplicatas, valores_suspeitos


class Concentracao(Regra):
    codigo = "concentracao"
    nome = "Concentração de contratos em um fornecedor"
    base_legal = "Lei 14.133/2021, art. 5º (princípio da competitividade); metodologia TCU"
    descricao = (f"O fornecedor recebeu mais de {int(PARAMS['concentracao_pct'] * 100)}% do valor contratado pelo "
                 f"órgão no ano (órgãos com pelo menos {PARAMS['concentracao_min_contratos']} contratos). Só entram "
                 "anos com coleta completa; contratos publicados em duplicidade contam uma vez, e um valor igual ao de "
                 "outro contrato do mesmo fornecedor e objeto com as casas decimais deslocadas (x100, x1000...) "
                 "fica de fora, por ser provável erro de digitação.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        if not contrato.data_assinatura or not contrato.valor_global:
            return None
        ano = contrato.data_assinatura.year
        suspeitos = valores_suspeitos(ctx)
        if ano not in anos_cobertos(ctx) or contrato.id in suspeitos:
            return None
        do_orgao = sem_duplicatas([c for c in ctx.contratos if c.orgao_id == contrato.orgao_id and c.data_assinatura
                                   and c.data_assinatura.year == ano and c.valor_global and c.id not in suspeitos],
                                  contrato)
        if len(do_orgao) < PARAMS["concentracao_min_contratos"]:
            return None
        total = sum(c.valor_global for c in do_orgao)
        do_fornecedor = sum(c.valor_global for c in do_orgao if c.fornecedor_id == contrato.fornecedor_id)
        pct = float(do_fornecedor / total)
        if pct <= PARAMS["concentracao_pct"]:
            return None
        return self.resultado(contrato, {"percentual": round(pct * 100, 1), "ano": ano,
                                         "total_orgao": fmt(total), "total_fornecedor": fmt(do_fornecedor),
                                         "contratos_orgao": len(do_orgao)})
