from ..extensions import db


class Sancao(db.Model):
    __tablename__ = "sancao"
    __table_args__ = (db.UniqueConstraint("documento", "cadastro", "data_inicio"),)
    id = db.Column(db.Integer, primary_key=True)
    documento = db.Column(db.String(14), nullable=False, index=True)
    cadastro = db.Column(db.String(4), nullable=False)
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    orgao_sancionador = db.Column(db.String(255))
    descricao = db.Column(db.Text)
