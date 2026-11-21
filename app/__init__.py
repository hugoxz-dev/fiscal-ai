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
    from .controllers import (api, contas, contratos, exportacao, fornecedores, metodologia, monitoramento, painel,
                              planos, politicos)
    from .controllers._acesso import conferir_csrf, csrf_token, usuario_atual
    from .views._filtros import registrar_filtros

    registrar_comandos(app)
    registrar_filtros(app)
    app.register_blueprint(painel.bp)
    app.register_blueprint(metodologia.bp)
    app.register_blueprint(contratos.bp)
    app.register_blueprint(fornecedores.bp)
    app.register_blueprint(politicos.bp)
    app.register_blueprint(contas.bp)
    app.register_blueprint(planos.bp)
    app.register_blueprint(monitoramento.bp)
    app.register_blueprint(exportacao.bp)
    app.register_blueprint(api.bp)
    app.before_request(conferir_csrf)

    @app.context_processor
    def _conta():
        from .services import monitoramento as mon
        from .services.contas import e_pro

        def novidades_qtd() -> int:
            u = usuario_atual()
            return mon.contar(u) if u is not None and e_pro(u) else 0

        return {"usuario_atual": usuario_atual, "e_pro_atual": lambda: e_pro(usuario_atual()),
                "csrf_token": csrf_token, "novidades_qtd": novidades_qtd,
                "segue": lambda tipo, alvo_id: mon.segue(usuario_atual(), tipo, alvo_id)}

    @app.context_processor
    def _aviso():
        return {"AVISO": ("Os alertas indicam indícios de risco calculados automaticamente e não "
                          "constituem acusação ou prova de irregularidade.")}

    return app
