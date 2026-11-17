from ..extensions import db
from ._tipos import Dinheiro, TextoLongo


class PublicacaoDiario(db.Model):
    __tablename__ = "publicacao_diario"
    id = db.Column(db.Integer, primary_key=True)
    data_edicao = db.Column(db.Date)
    numero_edicao = db.Column(db.String(30))
    url_pdf = db.Column(db.String(500), unique=True, nullable=False)
    texto = db.Column(TextoLongo)
    processado = db.Column(db.Boolean, nullable=False, default=False)

    extratos = db.relationship("ExtratoDiario", back_populates="publicacao", cascade="all, delete-orphan")


class ExtratoDiario(db.Model):
    __tablename__ = "extrato_diario"
    id = db.Column(db.Integer, primary_key=True)
    publicacao_id = db.Column(db.Integer, db.ForeignKey("publicacao_diario.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    documento_fornecedor = db.Column(db.String(14))
    valor = db.Column(Dinheiro)
    objeto = db.Column(db.Text)
    trecho = db.Column(db.Text)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contrato.id"))

    publicacao = db.relationship("PublicacaoDiario", back_populates="extratos")
    contrato = db.relationship("Contrato", back_populates="extratos")
