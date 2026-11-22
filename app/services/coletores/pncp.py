"""Coletor do PNCP (Portal Nacional de Contratações Públicas)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Callable

import click
import requests

from ...extensions import db
from ...models import Aditivo, ColetaLog, Contratacao, Contrato, Fornecedor, Orgao
from ..http import criar_sessao, get_json

CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP = "https://pncp.gov.br/api/pncp/v1"
MODALIDADES = range(1, 14)
JANELA_CONTRATACOES = 30
JANELA_CONTRATOS = 15  # janelas maiores estouram o tempo limite da API
TAMANHO_PAGINA = 50

GetFn = Callable[..., object]


# ---------- funções puras de conversão ----------

def _dinheiro(v) -> Decimal | None:
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def _data(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _so_digitos(v: str | None) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def eh_municipal_sao_luis(item: dict, ibge: str) -> bool:
    unidade = item.get("unidadeOrgao") or {}
    orgao = item.get("orgaoEntidade") or {}
    return unidade.get("codigoIbge") == ibge and orgao.get("esferaId") == "M"


def _orgao(item: dict) -> dict:
    o = item["orgaoEntidade"]
    return {"cnpj": o["cnpj"], "razao_social": o["razaoSocial"], "esfera": o.get("esferaId")}


def parse_contratacao(item: dict) -> dict:
    cnpj = item["orgaoEntidade"]["cnpj"]
    ano, seq = item["anoCompra"], item["sequencialCompra"]
    return {
        "numero_controle_pncp": item["numeroControlePNCP"],
        "orgao": _orgao(item),
        "ano": ano,
        "sequencial": seq,
        "modalidade_id": item.get("modalidadeId"),
        "modalidade_nome": item.get("modalidadeNome"),
        "amparo_legal": (item.get("amparoLegal") or {}).get("nome"),
        "objeto": item.get("objetoCompra"),
        "valor_estimado": _dinheiro(item.get("valorTotalEstimado")),
        "valor_homologado": _dinheiro(item.get("valorTotalHomologado")),
        "data_publicacao": _data(item.get("dataPublicacaoPncp")),
        "link_pncp": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}",
    }


def parse_contrato(item: dict) -> dict:
    cnpj = item["orgaoEntidade"]["cnpj"]
    ano, seq = item["anoContrato"], item["sequencialContrato"]
    documento = _so_digitos(item.get("niFornecedor"))
    return {
        "numero_controle_pncp": item["numeroControlePNCP"],
        "numero_controle_compra": item.get("numeroControlePncpCompra"),
        "orgao": _orgao(item),
        "fornecedor": {
            "documento": documento,
            "nome": item.get("nomeRazaoSocialFornecedor") or documento,
            "tipo": "PF" if len(documento) == 11 else "PJ",
        },
        "ano": ano,
        "sequencial": seq,
        "objeto": item.get("objetoContrato"),
        "valor_inicial": _dinheiro(item.get("valorInicial")),
        "valor_global": _dinheiro(item.get("valorGlobal")),
        "data_assinatura": _data(item.get("dataAssinatura")),
        "link_pncp": f"https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq}",
    }


def parse_termo(item: dict) -> dict:
    acrescimo = item.get("valorAcrescido") if item.get("qualificacaoAcrescimoSupressao") else 0
    return {
        "numero": str(item.get("numeroTermoContrato") or item.get("sequencialTermoContrato")),
        "valor_acrescimo": _dinheiro(acrescimo or 0),
        "valor_global": _dinheiro(item.get("valorGlobal")),
        # objeto e observação do termo, sem repetir quando são iguais (costumam declarar o % de acréscimo)
        "descricao": "\n\n".join(dict.fromkeys(t.strip() for t in (item.get("objetoTermoContrato"),
                                                                  item.get("informativoObservacao")) if t and t.strip()))
                     or None,
        "data": _data(item.get("dataAssinatura")),
        "origem": "pncp",
    }


def contar_fornecedores_resultado(resultados_por_item: dict[int, list]) -> int | None:
    """Nº de fornecedores distintos vencedores na compra.

    O PNCP só publica o vencedor de cada item, então uma compra com um único item
    sempre teria "1 fornecedor" — nesse caso não há informação e devolvemos None.
    """
    if len(resultados_por_item) < 2:
        return None
    docs = {r.get("niFornecedor") for rs in resultados_por_item.values() for r in (rs or [])
            if not r.get("dataCancelamento")}
    docs.discard(None)
    return len(docs) or None


# ---------- persistência (upsert) ----------

def _upsert_orgao(d: dict) -> Orgao:
    o = Orgao.query.filter_by(cnpj=d["cnpj"]).first() or Orgao(cnpj=d["cnpj"])
    o.razao_social, o.esfera = d["razao_social"], d["esfera"]
    db.session.add(o)
    return o


def _upsert_fornecedor(d: dict) -> Fornecedor:
    f = Fornecedor.query.filter_by(documento=d["documento"]).first()
    if f is None:
        f = Fornecedor(documento=d["documento"], nome=d["nome"], tipo=d["tipo"])
        db.session.add(f)
    return f


def upsert_contratacao(d: dict) -> Contratacao:
    c = Contratacao.query.filter_by(numero_controle_pncp=d["numero_controle_pncp"]).first()
    orgao = _upsert_orgao(d["orgao"])
    if c is None:
        c = Contratacao(numero_controle_pncp=d["numero_controle_pncp"], orgao=orgao)
        db.session.add(c)
    c.orgao = orgao
    for campo in ("ano", "sequencial", "modalidade_id", "modalidade_nome", "amparo_legal", "objeto",
                  "valor_estimado", "valor_homologado", "data_publicacao", "link_pncp"):
        setattr(c, campo, d[campo])
    return c


def upsert_contrato(d: dict) -> Contrato:
    c = Contrato.query.filter_by(numero_controle_pncp=d["numero_controle_pncp"]).first()
    orgao = _upsert_orgao(d["orgao"])
    fornecedor = _upsert_fornecedor(d["fornecedor"])
    if c is None:
        c = Contrato(numero_controle_pncp=d["numero_controle_pncp"], orgao=orgao, fornecedor=fornecedor)
        db.session.add(c)
    c.orgao, c.fornecedor = orgao, fornecedor
    for campo in ("ano", "sequencial", "objeto", "valor_inicial", "valor_global",
                  "data_assinatura", "link_pncp"):
        setattr(c, campo, d[campo])
    if d.get("numero_controle_compra"):
        compra = Contratacao.query.filter_by(numero_controle_pncp=d["numero_controle_compra"]).first()
        if compra is not None:
            c.contratacao = compra
            c.modalidade_id = compra.modalidade_id
    return c


def upsert_aditivo(contrato: Contrato, d: dict) -> Aditivo:
    a = next((x for x in contrato.aditivos if x.numero == d["numero"] and x.origem == d["origem"]), None)
    if a is None:
        a = Aditivo(numero=d["numero"], origem=d["origem"])
        contrato.aditivos.append(a)
    a.valor_acrescimo, a.valor_global, a.data = d["valor_acrescimo"], d.get("valor_global"), d["data"]
    a.descricao = d.get("descricao")
    return a


# ---------- coleta ----------

def _janelas(de: date, ate: date, dias: int):
    inicio = de
    while inicio <= ate:
        fim = min(inicio + timedelta(days=dias - 1), ate)
        yield inicio, fim
        inicio = fim + timedelta(days=1)


def _paginar(get: GetFn, url: str, params: dict):
    pagina = 1
    while True:
        resp = get(url, params={**params, "pagina": pagina, "tamanhoPagina": TAMANHO_PAGINA})
        if not resp:
            return
        yield from resp.get("data") or []
        if pagina >= (resp.get("totalPaginas") or 1):
            return
        pagina += 1


def _numero_compra_para_partes(numero: str) -> tuple[str, int, int]:
    # "06307102000130-1-000062/2025" -> ("06307102000130", 2025, 62)
    cnpj, _, resto = numero.split("-", 2)
    seq, ano = resto.split("/")
    return cnpj, int(ano), int(seq)


def _garantir_contratacao(get: GetFn, numero: str, ibge: str) -> None:
    existente = Contratacao.query.filter_by(numero_controle_pncp=numero).first()
    if existente and existente.amparo_legal:  # sem amparo: salva antes da coluna existir, busca de novo
        return
    cnpj, ano, seq = _numero_compra_para_partes(numero)
    item = get(f"{CONSULTA}/orgaos/{cnpj}/compras/{ano}/{seq}")
    if item and eh_municipal_sao_luis(item, ibge):
        upsert_contratacao(parse_contratacao(item))


def _atualizar_competicao(get: GetFn, compra: Contratacao) -> None:
    cnpj = compra.orgao.cnpj
    base = f"{PNCP}/orgaos/{cnpj}/compras/{compra.ano}/{compra.sequencial}/itens"
    itens = get(base, params={"pagina": 1, "tamanhoPagina": TAMANHO_PAGINA}) or []
    resultados = {}
    for item in itens:
        if item.get("temResultado"):
            n = item["numeroItem"]
            resultados[n] = get(f"{base}/{n}/resultados") or []
    compra.qtd_fornecedores_resultado = contar_fornecedores_resultado(resultados)


def coletar_pncp(de: date, ate: date, ibge: str, get: GetFn | None = None) -> int:
    """Coleta contratações, contratos, aditivos e resultados do município. Retorna nº de registros."""
    get_api = get or partial(get_json, criar_sessao())
    falhas: list[str] = []

    def get(url, params=None):
        """Uma consulta que falha (timeout, queda da API) é registrada e pulada, sem perder o resto."""
        try:
            return get_api(url, params=params)
        except requests.RequestException as exc:
            falhas.append(f"{url} {params or ''}: {exc}")
            click.echo(f"  falha ao consultar {url} ({exc.__class__.__name__}); seguindo")
            return None

    log = ColetaLog(fonte="pncp", inicio=datetime.now())
    db.session.add(log)
    total = 0
    try:
        # órgãos municipais já conhecidos também têm seus contratos consultados
        cnpjs: set[str] = {o.cnpj for o in Orgao.query.filter_by(esfera="M")}
        for ini, fim in _janelas(de, ate, JANELA_CONTRATACOES):
            for modalidade in MODALIDADES:
                params = {"dataInicial": ini.strftime("%Y%m%d"), "dataFinal": fim.strftime("%Y%m%d"),
                          "codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": ibge}
                for item in _paginar(get, f"{CONSULTA}/contratacoes/publicacao", params):
                    if eh_municipal_sao_luis(item, ibge):
                        upsert_contratacao(parse_contratacao(item))
                        cnpjs.add(item["orgaoEntidade"]["cnpj"])
                        total += 1
            db.session.commit()
            click.echo(f"  contratações até {fim:%d/%m/%Y}: {total}")

        contratos_novos: list[Contrato] = []
        for cnpj in sorted(cnpjs):
            for ini, fim in _janelas(de, ate, JANELA_CONTRATOS):
                params = {"dataInicial": ini.strftime("%Y%m%d"), "dataFinal": fim.strftime("%Y%m%d"),
                          "cnpjOrgao": cnpj}
                for item in _paginar(get, f"{CONSULTA}/contratos", params):
                    if not eh_municipal_sao_luis(item, ibge):
                        continue
                    d = parse_contrato(item)
                    if d["numero_controle_compra"]:
                        _garantir_contratacao(get, d["numero_controle_compra"], ibge)
                    contratos_novos.append(upsert_contrato(d))
                    total += 1
                db.session.commit()
            click.echo(f"  contratos do órgão {cnpj}: {len(contratos_novos)}")

        for c in contratos_novos:
            for termo in get(f"{PNCP}/orgaos/{c.orgao.cnpj}/contratos/{c.ano}/{c.sequencial}/termos") or []:
                if "aditivo" in (termo.get("tipoTermoContratoNome") or "").lower():
                    upsert_aditivo(c, parse_termo(termo))
                    total += 1
        db.session.commit()

        compras = {c.contratacao for c in contratos_novos if c.contratacao is not None}
        for compra in compras:
            if compra.modalidade_id not in (8, 9):
                _atualizar_competicao(get, compra)
        db.session.commit()
        log.status = "parcial" if falhas else "ok"
        log.erro = "\n".join(falhas[:20]) or None
    except Exception as exc:  # registra a falha e repassa
        db.session.rollback()
        log = ColetaLog(fonte="pncp", inicio=log.inicio, status="erro", erro=str(exc))
        db.session.add(log)
        raise
    finally:
        log.fim, log.registros = datetime.now(), total
        db.session.commit()
    return total
