from ..extensions import db
from ._tipos import Dinheiro


class Contratacao(db.Model):
    __tablename__ = "contratacao"
    id = db.Column(db.Integer, primary_key=True)
    numero_controle_pncp = db.Column(db.String(60), unique=True, nullable=False)
    orgao_id = db.Column(db.Integer, db.ForeignKey("orgao.id"), nullable=False)
    ano = db.Column(db.Integer)
    sequencial = db.Column(db.Integer)
    modalidade_id = db.Column(db.Integer)
    modalidade_nome = db.Column(db.String(80))
    objeto = db.Column(db.Text)
    valor_estimado = db.Column(Dinheiro)
    valor_homologado = db.Column(Dinheiro)
    data_publicacao = db.Column(db.Date)
    qtd_fornecedores_resultado = db.Column(db.Integer)
    link_pncp = db.Column(db.String(255))

    orgao = db.relationship("Orgao")
    contratos = db.relationship("Contrato", back_populates="contratacao")
