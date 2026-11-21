"""Executa as regras de risco, calcula o score e pede ao LLM as explicações."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..extensions import db
from ..models import Alerta, Contrato, Sancao
from .llm import get_llm  # noqa: F401  (reexportado para o CLI e para testes)
from .regras.aditivos import AditivosExcessivos
from .regras.base import Contexto, Regra
from .regras.cnae import CnaeIncompativel
from .regras.competicao import CompeticaoBaixa
from .regras.concentracao import Concentracao
from .regras.config import NIVEIS, PESOS
from .regras.dispensa import DispensaLimite
from .regras.fornecedor_novo import FornecedorNovo
from .regras.fracionamento import Fracionamento
from .regras.sancionado import Sancionado
from .regras.sobrepreco import Sobrepreco

REGRAS: list[type[Regra]] = [DispensaLimite, Fracionamento, FornecedorNovo, CnaeIncompativel, Sancionado,
                             Concentracao, CompeticaoBaixa, AditivosExcessivos, Sobrepreco]


def nivel_para(score: int) -> str:
    return next(nome for minimo, nome in NIVEIS if score >= minimo)


def _contexto(llm) -> Contexto:
    sancoes = defaultdict(list)
    for s in Sancao.query.all():
        sancoes[s.documento].append(s)
    return Contexto(contratos=Contrato.query.all(), sancoes=dict(sancoes), llm=llm)


def analisar_todos(llm) -> dict:
    ctx = _contexto(llm)
    regras = [cls(PESOS) for cls in REGRAS]
    for r in regras:
        if hasattr(r, "preparar"):
            r.preparar(ctx)
    resumo = {"contratos": 0, "alertas": 0, "alto": 0, "medio": 0, "baixo": 0}
    agora = datetime.now()
    for contrato in ctx.contratos:
        resultados = [res for r in regras if (res := r.avaliar(contrato, ctx)) is not None]
        # alerta que já existia na mesma regra mantém a data original (base das "novidades" do monitoramento)
        antigos = {a.regra_codigo: a.criado_em for a in contrato.alertas}
        contrato.alertas.clear()
        for res in resultados:
            contrato.alertas.append(Alerta(regra_codigo=res.codigo, pontos=res.pontos, evidencia=res.evidencia,
                                           criado_em=antigos.get(res.codigo, agora)))
        score = min(100, sum(res.pontos for res in resultados))
        if score != contrato.score:
            contrato.explicacao = None  # indícios mudaram: a explicação antiga não vale mais
        contrato.score, contrato.nivel, contrato.analisado_em = score, nivel_para(score), agora
        resumo["contratos"] += 1
        resumo["alertas"] += len(resultados)
        resumo[{"Alto": "alto", "Médio": "medio", "Baixo": "baixo"}[contrato.nivel]] += 1
    db.session.commit()
    return resumo


def _resumo_contrato(c: Contrato) -> dict:
    return {"objeto": c.objeto, "orgao": c.orgao.razao_social if c.orgao else None,
            "fornecedor": c.fornecedor.nome if c.fornecedor else None,
            "valor_global": str(c.valor_global), "data_assinatura": str(c.data_assinatura),
            "modalidade_id": c.modalidade_id, "score": c.score, "nivel": c.nivel}


def explicar_pendentes(llm, limite: int = 50) -> int:
    nomes = {cls.codigo: cls.nome for cls in REGRAS}
    pendentes = (Contrato.query.filter(Contrato.score > 0, Contrato.explicacao.is_(None))
                 .order_by(Contrato.score.desc()).limit(limite).all())
    feitos = 0
    for c in pendentes:
        alertas = [{"regra": nomes.get(a.regra_codigo, a.regra_codigo), "pontos": a.pontos,
                    "evidencia": a.evidencia} for a in c.alertas]
        texto = llm.explicar(_resumo_contrato(c), alertas)
        if texto:
            c.explicacao = texto
            feitos += 1
            db.session.commit()
    return feitos
