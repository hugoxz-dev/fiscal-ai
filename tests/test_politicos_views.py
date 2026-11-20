from decimal import Decimal

from app.extensions import db
from app.models import Doacao, Fornecedor, Politico, Socio
from app.services.texto import cpf_meio, normalizar

AVISO = "Ligação indica relação registrada em dados públicos, não irregularidade."
CPF_DOADOR = "11122233344"
CPF_POL = "12345678901"


def _pol(nome="Beltrano da Silva", cargo="Vereador", cpf=None, sq="1", **kw):
    p = Politico(nome=nome, nome_urna=kw.pop("nome_urna", nome), cargo=cargo, cpf=cpf, uf="MA",
                 partido="ABC", municipio="SÃO LUÍS", ano_eleicao=2024, sq_candidato=sq, **kw)
    p.atualizar_busca()
    db.session.add(p)
    db.session.commit()
    return p


def test_busca_sem_acento_e_minimo(client, app):
    _pol("São Luís Teste")
    assert len(client.get("/politicos/busca.json?q=sao luis").get_json()) == 1
    assert len(client.get("/politicos/busca.json?q=SÃO").get_json()) == 1
    assert client.get("/politicos/busca.json?q=s").get_json() == []
    assert client.get("/politicos/busca.json?q=").get_json() == []


def test_busca_nao_vaza_cpf(client, app):
    _pol("Fulano Cpf", cpf="12345678901")
    r = client.get("/politicos/busca.json?q=fulano")
    assert "12345678901" not in r.get_data(as_text=True)
    assert r.get_json()[0]["url"].startswith("/politicos/")


def test_ficha_sem_dados_abre(client, app):
    p = _pol("Sena Dor", cargo="Senador", sq=None)
    r = client.get(f"/politicos/{p.id}")
    assert r.status_code == 200
    assert "Não encontramos prestação de contas no TSE para este mandato" in r.get_data(as_text=True)


def test_ficha_mostra_ligacao_e_aviso_sem_cpf(client, app):
    f = Fornecedor(documento="12345678000199", nome="CONSTRUTORA ABC LTDA", tipo="PJ")
    db.session.add(f)
    db.session.commit()
    db.session.add(Socio(fornecedor=f, nome="Fulano de Tal", nome_norm=normalizar("Fulano de Tal"),
                         cpf_meio=cpf_meio(CPF_DOADOR)))
    p = _pol(cpf=CPF_POL)
    db.session.add(Doacao(politico=p, sq_receita="1", documento=CPF_DOADOR, nome="FULANO DE TAL",
                          nome_norm="FULANO DE TAL", valor=Decimal("500"), originario=False))
    db.session.commit()
    html = client.get(f"/politicos/{p.id}").get_data(as_text=True)
    assert "CONSTRUTORA ABC LTDA" in html
    assert AVISO in html
    assert CPF_DOADOR not in html and CPF_POL not in html


def test_ficha_so_nome_em_secao_separada(client, app):
    f = Fornecedor(documento="12345678901", nome="BELTRANO DA SILVA", tipo="PF")
    db.session.add(f)
    p = _pol(cpf=None)
    db.session.commit()
    html = client.get(f"/politicos/{p.id}").get_data(as_text=True)
    assert "nome igual — CPF não disponível para confirmar" in html


def test_lista_agrupada_e_menu(client, app):
    _pol("Vereador Um")
    r = client.get("/politicos")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Vereador" in html and 'href="/politicos"' in html
    assert "Vereador Um" in client.get("/politicos?q=vereador").get_data(as_text=True)
    assert "Vereador Um" not in client.get("/politicos?q=zzzz").get_data(as_text=True)


def test_ficha_404(client, app):
    assert client.get("/politicos/999").status_code == 404


def test_lista_selo_de_ligacao_neutro(client, app):
    f = Fornecedor(documento="12345678000199", nome="CONSTRUTORA ABC LTDA", tipo="PJ")
    db.session.add(f)
    db.session.commit()
    db.session.add(Socio(fornecedor=f, nome="Beltrano da Silva", nome_norm=normalizar("Beltrano da Silva"),
                         cpf_meio=cpf_meio(CPF_POL)))
    _pol(cpf=CPF_POL)
    html = client.get("/politicos").get_data(as_text=True)
    item = html[html.index("<li>"):html.index("</li>")]
    assert "nivel-" not in item
    assert "1 ligação" in item


def test_lista_e_ficha_mostram_foto_ou_iniciais(client, app):
    local = _pol("Ana Local", sq="10", foto_url="fotos/10.jpg")
    remoto = _pol("Bruno Remoto", cargo="Senador", sq="11", foto_url="http://senado/x.jpg")
    _pol("Carla Sem Foto", sq="12")
    html = client.get("/politicos").get_data(as_text=True)
    assert 'src="/static/fotos/10.jpg"' in html
    assert 'src="http://senado/x.jpg"' in html
    assert ">CF<" in html  # iniciais de quem não tem foto
    ficha = client.get(f"/politicos/{local.id}").get_data(as_text=True)
    assert 'src="/static/fotos/10.jpg"' in ficha
    assert remoto.id
