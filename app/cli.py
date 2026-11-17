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


# Ordem importa em "todas": contratos antes de enriquecer CNPJ e sanções.
FONTES = {
    "pncp": _coletar_pncp,
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
