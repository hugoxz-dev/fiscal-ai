def test_app_usa_sqlite_em_teste(app):
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")


def test_init_db_cria_tabelas(app, tmp_path):
    app.config["SCHEMA_SQL_PATH"] = str(tmp_path / "schema.sql")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    assert "Tabelas criadas" in result.output
