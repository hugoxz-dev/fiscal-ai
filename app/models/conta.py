"""Contas de usuário e plano Pro/Institucional (monetização em modo demonstração)."""
from datetime import datetime

from ..extensions import db
from ._tipos import Dinheiro


class Usuario(db.Model):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    ultima_visita_monitoramento = db.Column(db.DateTime)

    assinaturas = db.relationship("Assinatura", back_populates="usuario", cascade="all, delete-orphan")
    seguidos = db.relationship("Seguido", back_populates="usuario", cascade="all, delete-orphan")
    chaves = db.relationship("ChaveApi", back_populates="usuario", cascade="all, delete-orphan")


class Assinatura(db.Model):
    __tablename__ = "assinatura"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    plano = db.Column(db.String(20), nullable=False)  # pro | institucional
    periodo = db.Column(db.String(10), nullable=False)  # mensal | anual | manual
    valor = db.Column(Dinheiro, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="ativa")  # ativa | cancelada
    inicio = db.Column(db.Date, nullable=False)
    fim = db.Column(db.Date, nullable=False)

    usuario = db.relationship("Usuario", back_populates="assinaturas")


class Seguido(db.Model):
    __tablename__ = "seguido"
    __table_args__ = (db.UniqueConstraint("usuario_id", "tipo", "alvo_id", name="uq_seguido"),)
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(12), nullable=False)  # fornecedor | politico
    alvo_id = db.Column(db.Integer, nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    usuario = db.relationship("Usuario", back_populates="seguidos")


class ChaveApi(db.Model):
    __tablename__ = "chave_api"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    prefixo = db.Column(db.String(8), nullable=False)
    chave_hash = db.Column(db.String(64), unique=True, nullable=False)  # sha256; a chave completa não é guardada
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    revogada_em = db.Column(db.DateTime)

    usuario = db.relationship("Usuario", back_populates="chaves")
    usos = db.relationship("UsoApi", back_populates="chave", cascade="all, delete-orphan")


class UsoApi(db.Model):
    __tablename__ = "uso_api"
    __table_args__ = (db.UniqueConstraint("chave_id", "dia", name="uq_uso_api_dia"),)
    id = db.Column(db.Integer, primary_key=True)
    chave_id = db.Column(db.Integer, db.ForeignKey("chave_api.id"), nullable=False)
    dia = db.Column(db.Date, nullable=False)
    chamadas = db.Column(db.Integer, nullable=False, default=0)

    chave = db.relationship("ChaveApi", back_populates="usos")


class PedidoInstitucional(db.Model):
    __tablename__ = "pedido_institucional"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    orgao = db.Column(db.String(190), nullable=False)
    municipio = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), nullable=False)
    mensagem = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
