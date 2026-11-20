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


def _coletar_socios(de: date, ate: date, cfg) -> int:
    from .services.coletores.brasilapi import coletar_socios

    return coletar_socios()


def _coletar_sancoes(de: date, ate: date, cfg) -> int:
    from .services.coletores.transparencia import coletar_sancoes

    return coletar_sancoes()


def _coletar_convenios(de: date, ate: date, cfg) -> int:
    from .services.coletores.transparencia import coletar_convenios

    return coletar_convenios(de, ate, cfg["IBGE_MUNICIPIO"])


def _coletar_tse(de: date, ate: date, cfg) -> int:
    from .services.coletores.tse import coletar_tse

    return coletar_tse()


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
    "socios": _coletar_socios,
    "sancoes": _coletar_sancoes,
    "convenios": _coletar_convenios,
    "diario": _coletar_diario,
    "tse": _coletar_tse,
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
    @click.option("--fonte", default="todas", help="pncp | cnpj | socios | sancoes | convenios | diario | tse | todas")
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
            click.echo("Ollama indisponível — regra de CNAE usa só os julgamentos já guardados.")
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

    @app.cli.group("validacao")
    def validacao():
        """Validação manual dos alertas (amostra para conferir e resumo da precisão)."""

    @validacao.command("amostra")
    @click.option("--por-regra", default=5, show_default=True, help="Alertas sorteados de cada regra")
    @click.option("--semente", default=42, show_default=True, help="Semente do sorteio (mesma amostra sempre)")
    @click.option("--saida", default="validacao.csv", show_default=True, type=click.Path(dir_okay=False))
    @click.option("--url-painel", default="http://127.0.0.1:5000", show_default=True)
    def amostra(por_regra, semente, saida, url_painel):
        """Gera a planilha (CSV para o Excel) com uma amostra de alertas para conferência manual."""
        from .services.validacao import gravar_amostra, sortear_alertas

        alertas = sortear_alertas(por_regra, semente)
        gravar_amostra(saida, alertas, url_painel)
        click.echo(f"{len(alertas)} alertas gravados em {saida}. Preencha a coluna 'veredito' com "
                   "acerto, falso positivo ou inconclusivo e rode: flask validacao resumo " + saida)

    @validacao.command("resumo")
    @click.argument("planilha", type=click.Path(exists=True, dir_okay=False))
    def resumo(planilha):
        """Lê a planilha preenchida e mostra a precisão de cada regra (tabela pronta para a monografia)."""
        from .services.validacao import ErroValidacao, resumir, tabela_markdown

        try:
            click.echo(tabela_markdown(resumir(planilha)))
        except ErroValidacao as e:
            raise click.ClickException(str(e))
        click.echo("\nPrecisão = acertos / (acertos + falsos positivos); inconclusivos e pendentes ficam fora.")
