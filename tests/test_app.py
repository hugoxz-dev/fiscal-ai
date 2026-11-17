def test_app_usa_sqlite_em_teste(app):
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")


def test_init_db_cria_tabelas(app, tmp_path):
    app.config["SCHEMA_SQL_PATH"] = str(tmp_path / "schema.sql")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    assert "Tabelas criadas" in result.output


def test_init_db_grava_schema_mysql(app, tmp_path):
    destino = tmp_path / "schema.sql"
    app.config["SCHEMA_SQL_PATH"] = str(destino)
    app.test_cli_runner().invoke(args=["init-db"])
    sql = destino.read_text(encoding="utf-8")
    assert "CREATE TABLE contrato" in sql
    assert "LONGTEXT" in sql
