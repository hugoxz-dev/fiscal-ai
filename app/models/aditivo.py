from ..extensions import db
from ._tipos import Dinheiro


class Aditivo(db.Model):
    __tablename__ = "aditivo"
    __table_args__ = (db.UniqueConstraint("contrato_id", "numero", "origem"),)
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contrato.id"), nullable=False)
    numero = db.Column(db.String(30), nullable=False)
    valor_acrescimo = db.Column(Dinheiro, nullable=False, default=0)
    data = db.Column(db.Date)
    origem = db.Column(db.String(10), nullable=False)

    contrato = db.relationship("Contrato", back_populates="aditivos")
