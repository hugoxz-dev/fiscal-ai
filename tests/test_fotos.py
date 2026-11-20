import io
import zipfile

from app.extensions import db
from app.models import Politico
from app.services.coletores.fotos import URL_FOTOS, coletar_fotos


def _zip(arquivos: dict[str, bytes]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _politico(**kw):
    p = Politico(nome=kw.pop("nome", "FULANO"), cargo=kw.pop("cargo", "Vereador"), uf="MA", **kw)
    p.atualizar_busca()
    db.session.add(p)
    db.session.commit()
    return p


def test_baixa_foto_do_vereador_e_grava_caminho_local(app, tmp_path):
    p = _politico(sq_candidato="100002092730", ano_eleicao=2024)
    urls = []

    def abrir(url):
        urls.append(url)
        return _zip({"leiame.pdf": b"x", "FMA100002092730_div.jpeg": b"JPEGDATA", "FMA999_div.jpg": b"outro"})

    assert coletar_fotos(tmp_path, abrir_zip=abrir) == 1
    assert urls == [URL_FOTOS.format(ano=2024)]
    assert (tmp_path / "100002092730.jpg").read_bytes() == b"JPEGDATA"
    assert db.session.get(Politico, p.id).foto_url == "fotos/100002092730.jpg"


def test_nao_mexe_em_federal_nem_repete_quem_ja_tem_foto(app, tmp_path):
    _politico(cargo="Deputado Federal", sq_candidato="1", ano_eleicao=2022, foto_url="https://camara/x.jpg")
    p = _politico(sq_candidato="2", ano_eleicao=2024)
    abertos = []

    def abrir(url):
        abertos.append(url)
        return _zip({"FMA2_div.jpg": b"A"})

    assert coletar_fotos(tmp_path, abrir_zip=abrir) == 1
    assert coletar_fotos(tmp_path, abrir_zip=abrir) == 0  # já tem arquivo: não abre o zip de novo
    assert len(abertos) == 1
    assert db.session.get(Politico, p.id).foto_url == "fotos/2.jpg"


def test_zip_ausente_ou_sem_foto_segue(app, tmp_path):
    _politico(sq_candidato="3", ano_eleicao=2024)

    def abrir(url):
        raise KeyError(url)

    assert coletar_fotos(tmp_path, abrir_zip=abrir) == 0
    assert coletar_fotos(tmp_path, abrir_zip=lambda url: _zip({"FMA9_div.jpg": b"z"})) == 0
