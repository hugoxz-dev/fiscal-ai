from datetime import datetime

from ..extensions import db


class Alerta(db.Model):
    __tablename__ = "alerta"
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contrato.id"), nullable=False)
    regra_codigo = db.Column(db.String(30), nullable=False)
    pontos = db.Column(db.Integer, nullable=False)
    evidencia = db.Column(db.JSON, nullable=False, default=dict)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    contrato = db.relationship("Contrato", back_populates="alertas")
