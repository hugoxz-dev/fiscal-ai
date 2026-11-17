from flask import Flask

from .config import Config
from .extensions import db


def create_app(config_override: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="views")
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    db.init_app(app)

    from .cli import registrar_comandos
    from .controllers import metodologia, painel
    from .views._filtros import registrar_filtros

    registrar_comandos(app)
    registrar_filtros(app)
    app.register_blueprint(painel.bp)
    app.register_blueprint(metodologia.bp)

    @app.context_processor
    def _aviso():
        return {"AVISO": ("Os alertas indicam indícios de risco calculados automaticamente e não "
                          "constituem acusação ou prova de irregularidade.")}

    return app
