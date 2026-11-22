from __future__ import annotations

import re
import unicodedata

from ...models import Contrato
from .base import Contexto, Regra, Resultado

# "São Luís" sozinho ou seguido de MA — evita homônimos como São Luís de Montes Belos (GO).
_SAO_LUIS = re.compile(r"\bSAO LUIS\b\s*(?:$|[-/(,]\s*MA\b|\bMA\b)")


def _normalizar(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


def impede_contratar(sancao) -> bool:
    """A sanção impede São Luís de contratar? Inidoneidade vale para qualquer ente (Lei 14.133, art. 156,
    §5º); impedimento e suspensão só no ente que os aplicou (§4º); multa e publicação não impedem."""
    descricao = _normalizar(sancao.descricao)
    if "INIDONEIDADE" in descricao:
        return True
    if "IMPEDIMENTO" in descricao or "SUSPENSAO" in descricao or "PROIBICAO" in descricao:
        return bool(_SAO_LUIS.search(_normalizar(sancao.orgao_sancionador)))
    return False


class Sancionado(Regra):
    codigo = "sancionado"
    nome = "Fornecedor com sanção vigente"
    base_legal = "Lei 14.133/2021, art. 156, §§ 4º e 5º; Lei 12.846/2013 (CEIS/CNEP)"
    descricao = ("O fornecedor tinha, na data de assinatura do contrato, sanção vigente no CEIS ou no CNEP que o "
                 "impedia de contratar com São Luís: declaração de inidoneidade (vale para todos os entes) ou "
                 "impedimento/suspensão aplicado pelo próprio Município. Impedimentos de outros entes e multas "
                 "aparecem só na ficha do fornecedor.")

    def avaliar(self, contrato: Contrato, ctx: Contexto) -> Resultado | None:
        f, assinatura = contrato.fornecedor, contrato.data_assinatura
        if f is None or f.tipo != "PJ" or assinatura is None:
            return None
        vigentes = [s for s in ctx.sancoes.get(f.documento, [])
                    if s.data_inicio and s.data_inicio <= assinatura and (s.data_fim is None or s.data_fim >= assinatura)
                    and impede_contratar(s)]
        if not vigentes:
            return None
        return self.resultado(contrato, {"sancoes": [
            {"cadastro": s.cadastro, "inicio": s.data_inicio.isoformat(),
             "fim": s.data_fim.isoformat() if s.data_fim else None,
             "orgao_sancionador": s.orgao_sancionador, "descricao": s.descricao} for s in vigentes]})
