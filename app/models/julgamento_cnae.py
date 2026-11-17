from ..extensions import db


class JulgamentoCnae(db.Model):
    """Resposta do LLM sobre objeto x CNAE, guardada para não repetir a consulta a cada análise."""
    __tablename__ = "julgamento_cnae"
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contrato.id"), unique=True, nullable=False)
    cnae_descricao = db.Column(db.Text, nullable=False)  # atividades enviadas ao modelo
    objeto = db.Column(db.Text)
    modelo = db.Column(db.String(60))
    compativel = db.Column(db.Boolean, nullable=False)
    justificativa = db.Column(db.Text)
