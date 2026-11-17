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

    registrar_comandos(app)
    return app
