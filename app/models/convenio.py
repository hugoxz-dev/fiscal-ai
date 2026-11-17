from ..extensions import db
from ._tipos import Dinheiro


class Convenio(db.Model):
    __tablename__ = "convenio"
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), unique=True, nullable=False)
    orgao_concedente = db.Column(db.String(255))
    objeto = db.Column(db.Text)
    valor = db.Column(Dinheiro)
    data_inicio = db.Column(db.Date)
