from datetime import datetime

from ..extensions import db
from ._tipos import Dinheiro


class Contrato(db.Model):
    __tablename__ = "contrato"
    id = db.Column(db.Integer, primary_key=True)
    numero_controle_pncp = db.Column(db.String(60), unique=True, nullable=False)
    contratacao_id = db.Column(db.Integer, db.ForeignKey("contratacao.id"))
    orgao_id = db.Column(db.Integer, db.ForeignKey("orgao.id"), nullable=False)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"), nullable=False)
    ano = db.Column(db.Integer)
    sequencial = db.Column(db.Integer)
    objeto = db.Column(db.Text)
    valor_inicial = db.Column(Dinheiro)
    valor_global = db.Column(Dinheiro)
    data_assinatura = db.Column(db.Date)
    modalidade_id = db.Column(db.Integer)
    link_pncp = db.Column(db.String(255))
    score = db.Column(db.Integer, nullable=False, default=0)
    nivel = db.Column(db.String(10))
    explicacao = db.Column(db.Text)
    analisado_em = db.Column(db.DateTime)
    coletado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)  # entrada no banco; nunca muda

    orgao = db.relationship("Orgao", back_populates="contratos")
    fornecedor = db.relationship("Fornecedor", back_populates="contratos")
    contratacao = db.relationship("Contratacao", back_populates="contratos")
    aditivos = db.relationship("Aditivo", back_populates="contrato", cascade="all, delete-orphan")
    alertas = db.relationship("Alerta", back_populates="contrato", cascade="all, delete-orphan")
    extratos = db.relationship("ExtratoDiario", back_populates="contrato")

    def __init__(self, **kw):
        kw.setdefault("score", 0)
        super().__init__(**kw)
