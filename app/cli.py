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


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas no banco configurado e grava sql/schema.sql."""
        from . import models  # noqa: F401

        db.create_all()
        gravar_schema_sql(current_app.config["SCHEMA_SQL_PATH"])
        click.echo("Tabelas criadas.")
