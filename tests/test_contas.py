from app import create_app
from app.extensions import db
from app.models import Usuario


def _entrar(client, email="ana@x.com", senha="segredo123", next_=None):
    url = "/entrar" + (f"?next={next_}" if next_ else "")
    return client.post(url, data={"email": email, "senha": senha})


def test_cadastro_normaliza_email_e_guarda_hash(client, app):
    r = client.post("/cadastro", data={"nome": "Ana", "email": " Ana@X.com ", "senha": "segredo123"})
    assert r.status_code == 302
    u = Usuario.query.one()
    assert u.email == "ana@x.com" and u.senha_hash != "segredo123"


def test_cadastro_duplicado_mostra_erro(client, fazer_usuario):
    fazer_usuario()
    r = client.post("/cadastro", data={"nome": "Ana", "email": "ANA@x.com", "senha": "segredo123"})
    assert r.status_code == 200 and "já está cadastrado" in r.get_data(as_text=True)
    assert Usuario.query.count() == 1


def test_cadastro_senha_curta(client):
    r = client.post("/cadastro", data={"nome": "Ana", "email": "ana@x.com", "senha": "curta"})
    assert r.status_code == 200 and "8 caracteres" in r.get_data(as_text=True)
    assert Usuario.query.count() == 0


def test_login_com_email_em_maiusculas(client, fazer_usuario):
    fazer_usuario()
    r = _entrar(client, email="ANA@x.com")
    assert r.status_code == 302 and r.headers["Location"].endswith("/conta")
    assert client.get("/conta").status_code == 200


def test_login_senha_errada(client, fazer_usuario):
    fazer_usuario()
    r = _entrar(client, senha="errada123")
    assert r.status_code == 200 and "E-mail ou senha inválidos" in r.get_data(as_text=True)


def test_next_interno_respeitado(client, fazer_usuario):
    fazer_usuario()
    assert _entrar(client, next_="/contratos").headers["Location"].endswith("/contratos")


def test_next_externo_ignorado(client, fazer_usuario):
    fazer_usuario()
    for n in ("https://evil.com", "//evil.com", "/\\evil.com"):
        r = _entrar(client, next_=n)
        assert r.headers["Location"].endswith("/conta"), n


def test_conta_exige_login(client):
    r = client.get("/conta")
    assert r.status_code == 302 and "/entrar?next=/conta" in r.headers["Location"]


def test_sair(client, fazer_usuario, logar):
    logar(client, fazer_usuario())
    client.post("/sair")
    assert client.get("/conta").status_code == 302


def test_nav_mostra_entrar_ou_conta(client, fazer_usuario, logar):
    html = client.get("/").get_data(as_text=True)
    assert "Entrar" in html and "/planos" in html
    logar(client, fazer_usuario())
    assert "Minha conta" in client.get("/").get_data(as_text=True)


def test_post_sem_csrf_recusado():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "CSRF_ATIVO": True})
    with app.app_context():
        db.create_all()
        c = app.test_client()
        assert c.post("/entrar", data={"email": "a@x.com", "senha": "x"}).status_code == 400
        c.get("/entrar")
        with c.session_transaction() as s:
            token = s["csrf"]
        assert c.post("/entrar", data={"email": "a@x.com", "senha": "x", "csrf": token}).status_code == 200
        db.drop_all()


def test_painel_publico_continua_sem_login(client):
    for url in ("/", "/contratos", "/politicos", "/metodologia"):
        assert client.get(url).status_code == 200, url


def test_next_com_caractere_de_controle_ignorado(client, fazer_usuario):
    fazer_usuario()
    for n in ("/%09/evil.com", "/%0A/evil.com", "/%0D/evil.com"):
        r = _entrar(client, next_=n)
        assert r.status_code == 302 and r.headers["Location"].endswith("/conta"), n
