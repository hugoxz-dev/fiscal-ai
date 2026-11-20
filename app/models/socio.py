from ..extensions import db


class Socio(db.Model):
    __tablename__ = "socio"
    __table_args__ = (db.UniqueConstraint("fornecedor_id", "nome", name="uq_socio_fornecedor_nome"),)
    id = db.Column(db.Integer, primary_key=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"), nullable=False)
    nome = db.Column(db.String(255))
    nome_norm = db.Column(db.String(255), index=True)
    cpf_meio = db.Column(db.String(6), nullable=True, index=True)
    qualificacao = db.Column(db.String(100))
    data_entrada = db.Column(db.Date)

    fornecedor = db.relationship("Fornecedor", back_populates="socios")
