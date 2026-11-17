from __future__ import annotations

from ...models import Contrato
from .base import Contexto, Regra, Resultado


class Sancionado(Regra):
    codigo = "sancionado"
    nome = "Fornecedor com sanção vigente"
    base_legal = "Lei 14.133/2021, art. 156; Lei 12.846/2013 (CEIS/CNEP)"
    descricao = "O fornecedor constava no CEIS ou no CNEP com sanção vigente na data de assinatura do contrato."

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        f, assinatura = contrato.fornecedor, contrato.data_assinatura
        if f is None or f.tipo != "PJ" or assinatura is None:
            return None
        vigentes = [s for s in ctx.sancoes.get(f.documento, [])
                    if s.data_inicio and s.data_inicio <= assinatura and (s.data_fim is None or s.data_fim >= assinatura)]
        if not vigentes:
            return None
        return self.resultado(contrato, {"sancoes": [
            {"cadastro": s.cadastro, "inicio": s.data_inicio.isoformat(),
             "fim": s.data_fim.isoformat() if s.data_fim else None,
             "orgao_sancionador": s.orgao_sancionador, "descricao": s.descricao} for s in vigentes]})
