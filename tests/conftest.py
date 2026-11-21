import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "CSRF_ATIVO": False})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def fazer_contrato(app):
    """Fábrica de contratos persistidos; cria órgão/fornecedor padrão quando não informados."""
    from datetime import date
    from decimal import Decimal

    from app.models import Contrato, Fornecedor, Orgao

    contador = {"n": 0}

    def fazer(**kw):
        contador["n"] += 1
        orgao = kw.pop("orgao", None) or Orgao.query.filter_by(cnpj="06307102000130").first() \
            or Orgao(cnpj="06307102000130", razao_social="MUNICIPIO DE SAO LUIS", esfera="M")
        fornecedor = kw.pop("fornecedor", None) or Fornecedor.query.filter_by(documento="12345678000199").first() \
            or Fornecedor(documento="12345678000199", nome="EMPRESA PADRAO LTDA", tipo="PJ")
        valor = kw.pop("valor_global", Decimal("10000.00"))
        dados = dict(numero_controle_pncp=f"06307102000130-2-{contador['n']:06d}/2025", objeto="Aquisição de material",
                     valor_inicial=kw.pop("valor_inicial", valor), valor_global=valor,
                     data_assinatura=date(2025, 5, 1), modalidade_id=6)
        dados.update(kw)
        c = Contrato(orgao=orgao, fornecedor=fornecedor, **dados)
        db.session.add(c)
        db.session.commit()
        return c

    return fazer


@pytest.fixture
def ctx_vazio():
    from app.services.regras.base import Contexto

    return Contexto(contratos=[], sancoes={}, llm=None)


@pytest.fixture
def fazer_usuario(app):
    """Fábrica de usuários; com `plano`, cria assinatura ativa (fim padrão: hoje + 30)."""
    from datetime import date, timedelta
    from decimal import Decimal

    from werkzeug.security import generate_password_hash

    from app.models import Assinatura, Usuario

    def fazer(email="ana@x.com", senha="segredo123", plano=None, fim=None, nome="Ana"):
        u = Usuario(nome=nome, email=email, senha_hash=generate_password_hash(senha))
        if plano:
            u.assinaturas.append(Assinatura(plano=plano, periodo="mensal", valor=Decimal("19.90"), status="ativa",
                                            inicio=date.today(), fim=fim or date.today() + timedelta(days=30)))
        db.session.add(u)
        db.session.commit()
        return u

    return fazer


@pytest.fixture
def logar():
    def entrar(client, usuario):
        with client.session_transaction() as s:
            s["usuario_id"] = usuario.id

    return entrar
