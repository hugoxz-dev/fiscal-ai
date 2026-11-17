from ..extensions import db


class Orgao(db.Model):
    __tablename__ = "orgao"
    id = db.Column(db.Integer, primary_key=True)
    cnpj = db.Column(db.String(14), unique=True, nullable=False)
    razao_social = db.Column(db.String(255), nullable=False)
    esfera = db.Column(db.String(1))

    contratos = db.relationship("Contrato", back_populates="orgao")
