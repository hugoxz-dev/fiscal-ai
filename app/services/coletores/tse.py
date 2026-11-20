"""Coleta do TSE: eleitos de São Luís (2024), bens declarados e doações de campanha (só Maranhão)."""
from __future__ import annotations

import csv
from datetime import date, datetime
from typing import Callable, Iterator, TextIO

from ...extensions import db
from ...models import BemDeclarado, Doacao, Politico
from ..texto import cpf_valido, digitos, dinheiro_br, normalizar
from .zip_remoto import abrir_membro

BASE_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
NULOS = {"#NULO", "#NULO#", "#NE", "-1", "-3", "-4"}
ZIPS = {
    "consulta_cand": BASE_TSE + "/consulta_cand/consulta_cand_{ano}.zip",
    "bem_candidato": BASE_TSE + "/bem_candidato/bem_candidato_{ano}.zip",
    "receitas": BASE_TSE + "/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip",
}
CARGOS_MUNICIPAIS = {"PREFEITO": "Prefeito", "VEREADOR": "Vereador"}
CARGOS_FEDERAIS = {"Deputado Federal": "DEPUTADO FEDERAL", "Senador": "SENADOR"}


def ler_csv(arquivo: TextIO) -> Iterator[dict]:
    for linha in csv.DictReader(arquivo, delimiter=";"):
        yield {k: (None if v is None or v.strip() in NULOS else v.strip()) for k, v in linha.items()}


def _data(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%d/%m/%Y").date() if s else None
    except ValueError:
        return None


def _linhas(abrir: Callable, tipo: str, prefixo: str, ano: int) -> list[dict]:
    """Linhas do membro do ano; lista vazia quando o zip/membro não existe."""
    membro = f"{prefixo}_{ano}_MA.csv"
    try:
        arq = abrir(ZIPS[tipo].format(ano=ano), membro)
    except KeyError:
        return []
    with arq:
        return list(ler_csv(arq))


def _eleito(l: dict) -> bool:
    return (l.get("DS_SIT_TOT_TURNO") or "").upper().startswith("ELEITO")


def _eleitos_municipais(abrir) -> None:
    for l in _linhas(abrir, "consulta_cand", "consulta_cand", 2024):
        cargo = CARGOS_MUNICIPAIS.get(normalizar(l.get("DS_CARGO")))
        if normalizar(l.get("NM_UE")) != "SAO LUIS" or not cargo or not _eleito(l) or not l.get("SQ_CANDIDATO"):
            continue
        p = Politico.query.filter_by(sq_candidato=l["SQ_CANDIDATO"]).first() or Politico()
        p.sq_candidato = l["SQ_CANDIDATO"]
        p.nome = l.get("NM_CANDIDATO") or l.get("NM_URNA_CANDIDATO") or ""
        p.nome_urna = l.get("NM_URNA_CANDIDATO")
        p.partido = l.get("SG_PARTIDO")
        p.cargo = cargo
        p.municipio, p.uf, p.ano_eleicao = "São Luís", "MA", 2024
        p.cpf = cpf_valido(l.get("NR_CPF_CANDIDATO")) or p.cpf
        p.atualizar_busca()
        db.session.add(p)
    db.session.flush()


def _vincular_federais(abrir) -> None:
    pendentes = [p for p in Politico.query.filter(
        Politico.sq_candidato.is_(None),
        db.or_(Politico.id_camara.isnot(None), Politico.id_senado.isnot(None))).all()
        if p.cargo in CARGOS_FEDERAIS]
    for ano in (2022, 2018):
        # 2018 só vale para senadores (mandato de 8 anos); deputados federais: só 2022
        restantes = [p for p in pendentes if not p.sq_candidato and (ano == 2022 or p.cargo == "Senador")]
        if not restantes:
            break
        linhas = _linhas(abrir, "consulta_cand", "consulta_cand", ano)
        for p in restantes:
            alvo = CARGOS_FEDERAIS[p.cargo]
            for l in linhas:
                if normalizar(l.get("DS_CARGO")) != alvo or not _eleito(l) or not l.get("SQ_CANDIDATO"):
                    continue
                if p.cpf:
                    casa = cpf_valido(l.get("NR_CPF_CANDIDATO")) == p.cpf
                else:
                    casa = normalizar(l.get("NM_CANDIDATO")) == normalizar(p.nome)
                if casa and not Politico.query.filter_by(sq_candidato=l["SQ_CANDIDATO"]).first():
                    p.sq_candidato = l["SQ_CANDIDATO"]
                    p.ano_eleicao = ano
                    p.cpf = p.cpf or cpf_valido(l.get("NR_CPF_CANDIDATO"))
                    break
        db.session.flush()


def _bens(abrir, ano: int, por_sq: dict[str, Politico]) -> None:
    novos: dict[int, list[BemDeclarado]] = {}
    for l in _linhas(abrir, "bem_candidato", "bem_candidato", ano):
        p = por_sq.get(l.get("SQ_CANDIDATO"))
        if p:
            novos.setdefault(p.id, []).append(BemDeclarado(
                politico_id=p.id, tipo=l.get("DS_TIPO_BEM_CANDIDATO"),
                descricao=l.get("DS_BEM_CANDIDATO"), valor=dinheiro_br(l.get("VR_BEM_CANDIDATO"))))
    for pid, bens in novos.items():
        BemDeclarado.query.filter_by(politico_id=pid).delete()
        db.session.add_all(bens)
    db.session.flush()


def _gravar_doacao(p: Politico, sq_receita, documento, nome, origem, valor, data, originario) -> None:
    documento = digitos(documento)
    sq_receita = sq_receita or ""
    d = Doacao.query.filter_by(politico_id=p.id, sq_receita=sq_receita, originario=originario,
                               documento=documento).first()
    if d is None:
        d = Doacao(politico_id=p.id, sq_receita=sq_receita, originario=originario, documento=documento)
        db.session.add(d)
    d.nome, d.nome_norm, d.origem = nome, normalizar(nome), origem
    d.valor, d.data = dinheiro_br(valor), _data(data)
    db.session.flush()


def _doacoes(abrir, ano: int, por_sq: dict[str, Politico]) -> int:
    n = 0
    prestadores: dict[str, Politico] = {}
    for l in _linhas(abrir, "receitas", "receitas_candidatos", ano):
        p = por_sq.get(l.get("SQ_CANDIDATO"))
        if not p:
            continue
        if l.get("SQ_PRESTADOR_CONTAS"):
            prestadores[l["SQ_PRESTADOR_CONTAS"]] = p
        _gravar_doacao(p, l.get("SQ_RECEITA"), l.get("NR_CPF_CNPJ_DOADOR"), l.get("NM_DOADOR"),
                       l.get("DS_ORIGEM_RECEITA"), l.get("VR_RECEITA"), l.get("DT_RECEITA"), False)
        n += 1
    for l in _linhas(abrir, "receitas", "receitas_candidatos_doador_originario", ano):
        p = prestadores.get(l.get("SQ_PRESTADOR_CONTAS"))
        if not p:
            continue
        _gravar_doacao(p, l.get("SQ_RECEITA"), l.get("NR_CPF_CNPJ_DOADOR_ORIGINARIO"),
                       l.get("NM_DOADOR_ORIGINARIO"), None, l.get("VR_RECEITA"), l.get("DT_RECEITA"), True)
        n += 1
    return n


def coletar_tse(abrir: Callable[[str, str], TextIO] | None = None) -> int:
    """Retorna o número de doações gravadas (diretas + originárias)."""
    abrir = abrir or abrir_membro
    _eleitos_municipais(abrir)
    _vincular_federais(abrir)
    doacoes = 0
    candidatos = Politico.query.filter(Politico.sq_candidato.isnot(None)).all()
    for ano in sorted({p.ano_eleicao for p in candidatos if p.ano_eleicao}):
        por_sq = {p.sq_candidato: p for p in candidatos if p.ano_eleicao == ano}
        _bens(abrir, ano, por_sq)
        doacoes += _doacoes(abrir, ano, por_sq)
    db.session.commit()
    return doacoes
