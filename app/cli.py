import click
from flask import Flask

from .extensions import db


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas no banco configurado."""
        db.create_all()
        click.echo("Tabelas criadas.")
