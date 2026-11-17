from ..extensions import db
from ._tipos import Dinheiro


class Fornecedor(db.Model):
    __tablename__ = "fornecedor"
    id = db.Column(db.Integer, primary_key=True)
    documento = db.Column(db.String(14), unique=True, nullable=False)
    nome = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(2), nullable=False, default="PJ")
    data_abertura = db.Column(db.Date)
    capital_social = db.Column(Dinheiro)
    cnae_codigo = db.Column(db.String(10))
    cnae_descricao = db.Column(db.String(255))
    cnaes_secundarios = db.Column(db.Text)
    natureza_juridica = db.Column(db.String(10))  # código da Receita (ex.: 2062 Ltda, 3999 associação)
    situacao = db.Column(db.String(50))
    enriquecido_em = db.Column(db.DateTime)

    contratos = db.relationship("Contrato", back_populates="fornecedor")
