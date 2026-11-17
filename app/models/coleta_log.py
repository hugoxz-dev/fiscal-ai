from ..extensions import db


class ColetaLog(db.Model):
    __tablename__ = "coleta_log"
    id = db.Column(db.Integer, primary_key=True)
    fonte = db.Column(db.String(20), nullable=False)
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime)
    registros = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="ok")
    erro = db.Column(db.Text)
