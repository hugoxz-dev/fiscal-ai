"""Serialização para CSV e API. Mesma regra de privacidade do site: CPF de pessoa física sai mascarado,
e CPF de sócio, doador ou político nunca sai."""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from flask import url_for

from ..models import Alerta, Contrato, Fornecedor
from ..views._filtros import cnpj, modalidade
from .ligacoes import ligacoes_do_fornecedor

BOM = "\ufeff"  # Excel abre o CSV com acentos


def documento_publico(f: Fornecedor) -> str:
    return cnpj(f.documento)


def _dec(v) -> str | None:
    return None if v is None else f"{Decimal(v):.2f}"


def _br(v) -> str:
    return "" if v is None else f"{Decimal(v):.2f}".replace(".", ",")


def fornecedor_resumo(f: Fornecedor) -> dict:
    return {"id": f.id, "nome": f.nome, "documento": documento_publico(f), "tipo": f.tipo}


def alerta_dict(a: Alerta) -> dict:
    return {"regra_codigo": a.regra_codigo, "pontos": a.pontos, "evidencia": a.evidencia,
            "criado_em": a.criado_em.isoformat(timespec="seconds") if a.criado_em else None}


def contrato_dict(c: Contrato, com_alertas: bool = False) -> dict:
    d = {"id": c.id, "numero_controle_pncp": c.numero_controle_pncp, "objeto": c.objeto,
         "orgao": c.orgao.razao_social if c.orgao else None, "fornecedor": fornecedor_resumo(c.fornecedor),
         "valor_inicial": _dec(c.valor_inicial), "valor_global": _dec(c.valor_global),
         "data_assinatura": c.data_assinatura.isoformat() if c.data_assinatura else None,
         "modalidade": modalidade(c.modalidade_id), "score": c.score, "nivel": c.nivel, "link_pncp": c.link_pncp,
         "url": url_for("contratos.detalhe", id=c.id, _external=True)}
    if com_alertas:
        d["alertas"] = [alerta_dict(a) for a in sorted(c.alertas, key=lambda a: -a.pontos)]
    return d


def fornecedor_dict(f: Fornecedor) -> dict:
    d = fornecedor_resumo(f)
    d["url"] = url_for("fornecedores.detalhe", id=f.id, _external=True)
    d["contratos"] = [contrato_dict(c) for c in sorted(f.contratos, key=lambda c: -c.score)]
    d["alertas"] = [{"contrato_id": c.id, **alerta_dict(a)} for c in f.contratos for a in c.alertas]
    d["ligacoes"] = [{"tipo": l.tipo, "confirmada": l.confirmada,
                      "politico": {"id": l.politico.id, "nome": l.politico.nome_urna or l.politico.nome,
                                   "cargo": l.politico.cargo, "partido": l.politico.partido},
                      "pessoa": l.pessoa, "valor": _dec(l.valor), "descricao": l.descricao}
                     for l in ligacoes_do_fornecedor(f)]
    return d


def _csv(cabecalho: list[str], linhas) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(cabecalho)
    w.writerows(linhas)
    return BOM + buf.getvalue()


def contratos_csv(contratos) -> str:
    return _csv(["Score", "Nível", "Objeto", "Fornecedor", "CNPJ/CPF", "Órgão", "Modalidade", "Valor inicial",
                 "Valor global", "Assinatura", "Número PNCP", "Link PNCP"],
                ([c.score, c.nivel or "", c.objeto or "", c.fornecedor.nome, documento_publico(c.fornecedor),
                  c.orgao.razao_social if c.orgao else "", modalidade(c.modalidade_id), _br(c.valor_inicial),
                  _br(c.valor_global), c.data_assinatura.strftime("%d/%m/%Y") if c.data_assinatura else "",
                  c.numero_controle_pncp, c.link_pncp or ""] for c in contratos))


def alertas_csv(f: Fornecedor) -> str:
    linhas = ([c.numero_controle_pncp, c.objeto or "", a.regra_codigo, a.pontos, c.score, c.nivel or "",
               a.criado_em.strftime("%d/%m/%Y %H:%M") if a.criado_em else ""]
              for c in sorted(f.contratos, key=lambda c: -c.score) for a in sorted(c.alertas, key=lambda a: -a.pontos))
    return _csv(["Contrato PNCP", "Objeto", "Regra", "Pontos", "Score do contrato", "Nível", "Detectado em"], linhas)
