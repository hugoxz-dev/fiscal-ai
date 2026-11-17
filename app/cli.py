from datetime import date
from pathlib import Path

import click
from flask import Flask, current_app
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from .extensions import db


def gravar_schema_sql(destino: str) -> None:
    """Gera o DDL MySQL de todas as tabelas (para o Workbench e a monografia)."""
    from . import models  # noqa: F401  (garante que os modelos estão registrados)

    partes = [str(CreateTable(t).compile(dialect=mysql.dialect())).strip() + ";"
              for t in db.metadata.sorted_tables]
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n\n".join(partes) + "\n", encoding="utf-8")


def _coletar_pncp(de: date, ate: date, cfg) -> int:
    from .services.coletores.pncp import coletar_pncp

    return coletar_pncp(de, ate, cfg["IBGE_MUNICIPIO"])


def _coletar_cnpj(de: date, ate: date, cfg) -> int:
    from .services.coletores.brasilapi import enriquecer_fornecedores

    return enriquecer_fornecedores()


def _coletar_sancoes(de: date, ate: date, cfg) -> int:
    from .services.coletores.transparencia import coletar_sancoes

    return coletar_sancoes()


def _coletar_convenios(de: date, ate: date, cfg) -> int:
    from .services.coletores.transparencia import coletar_convenios

    return coletar_convenios(de, ate, cfg["IBGE_MUNICIPIO"])


def _coletar_diario(de: date, ate: date, cfg) -> int:
    from .services.coletores.diario_oficial import coletar_diario
    from .services.llm import get_llm

    llm = get_llm()
    if not llm.disponivel():
        click.echo("Ollama indisponível — edições serão baixadas e os extratos ficam pendentes.")
    return coletar_diario(de, ate, llm)


# Ordem importa em "todas": contratos antes de enriquecer CNPJ e sanções.
FONTES = {
    "pncp": _coletar_pncp,
    "cnpj": _coletar_cnpj,
    "sancoes": _coletar_sancoes,
    "convenios": _coletar_convenios,
    "diario": _coletar_diario,
}


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas no banco configurado e grava sql/schema.sql."""
        from . import models  # noqa: F401

        db.create_all()
        gravar_schema_sql(current_app.config["SCHEMA_SQL_PATH"])
        click.echo("Tabelas criadas.")

    @app.cli.command("coletar")
    @click.option("--fonte", default="todas", help="pncp | cnpj | sancoes | convenios | diario | todas")
    @click.option("--de", "de", default=None, help="Data inicial AAAA-MM-DD (padrão: COLETA_INICIO)")
    @click.option("--ate", "ate", default=None, help="Data final AAAA-MM-DD (padrão: hoje)")
    def coletar(fonte, de, ate):
        """Coleta dados das fontes públicas."""
        cfg = current_app.config
        if fonte != "todas" and fonte not in FONTES:
            raise click.BadParameter(f"fonte desconhecida: {fonte}. Opções: {', '.join(FONTES)}, todas")
        d_ini = date.fromisoformat(de or cfg["COLETA_INICIO"])
        d_fim = date.fromisoformat(ate) if ate else date.today()
        nomes = list(FONTES) if fonte == "todas" else [fonte]
        for nome in nomes:
            click.echo(f"Coletando {nome} de {d_ini:%d/%m/%Y} a {d_fim:%d/%m/%Y}...")
            n = FONTES[nome](d_ini, d_fim, cfg)
            click.echo(f"{nome}: {n} registros")

    @app.cli.command("analisar")
    def analisar():
        """Aplica as regras de risco a todos os contratos e calcula o score."""
        from .services import analisador

        llm = analisador.get_llm()
        if not llm.disponivel():
            click.echo("Ollama indisponível — regra de CNAE ignorada.")
            llm = None
        r = analisador.analisar_todos(llm)
        click.echo(f"Contratos: {r['contratos']} | Alertas: {r['alertas']} | "
                   f"Alto: {r['alto']} | Médio: {r['medio']} | Baixo: {r['baixo']}")

    @app.cli.command("explicar")
    @click.option("--limite", default=50, show_default=True, help="Máximo de contratos a explicar")
    def explicar(limite):
        """Gera com o LLM a explicação em português dos contratos com alertas."""
        from .services import analisador

        llm = analisador.get_llm()
        if not llm.disponivel():
            click.echo("Ollama indisponível — nada a fazer. Inicie o Ollama e rode de novo.")
            return
        click.echo(f"Explicações geradas: {analisador.explicar_pendentes(llm, limite)}")
