from ..extensions import db
from ..services.texto import normalizar
from ._tipos import Dinheiro


class Politico(db.Model):
    __tablename__ = "politico"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    nome_urna = db.Column(db.String(255))
    nome_busca = db.Column(db.String(600), index=True)
    cpf = db.Column(db.String(11), nullable=True)
    cargo = db.Column(db.String(20))  # Prefeito | Vereador | Deputado Federal | Senador
    partido = db.Column(db.String(30))
    uf = db.Column(db.String(2))
    municipio = db.Column(db.String(100), nullable=True)
    ano_eleicao = db.Column(db.Integer, nullable=True)
    sq_candidato = db.Column(db.String(20), unique=True, nullable=True)
    id_camara = db.Column(db.Integer, unique=True, nullable=True)
    id_senado = db.Column(db.Integer, unique=True, nullable=True)
    foto_url = db.Column(db.String(255))
    em_exercicio = db.Column(db.Boolean, default=True)

    bens = db.relationship("BemDeclarado", back_populates="politico", cascade="all, delete-orphan")
    doacoes = db.relationship("Doacao", back_populates="politico", cascade="all, delete-orphan")
    emendas = db.relationship("Emenda", back_populates="politico", cascade="all, delete-orphan")
    proposicoes = db.relationship("Proposicao", back_populates="politico", cascade="all, delete-orphan")
    despesas = db.relationship("DespesaParlamentar", back_populates="politico", cascade="all, delete-orphan")

    def atualizar_busca(self) -> None:
        self.nome_busca = normalizar(" ".join(filter(None, [self.nome, self.nome_urna, self.partido, self.cargo])))


class BemDeclarado(db.Model):
    __tablename__ = "bem_declarado"
    id = db.Column(db.Integer, primary_key=True)
    politico_id = db.Column(db.Integer, db.ForeignKey("politico.id"), nullable=False)
    tipo = db.Column(db.String(255))
    descricao = db.Column(db.Text)
    valor = db.Column(Dinheiro)

    politico = db.relationship("Politico", back_populates="bens")


class Doacao(db.Model):
    __tablename__ = "doacao"
    __table_args__ = (db.UniqueConstraint("politico_id", "sq_receita", "originario", "documento",
                                          name="uq_doacao"),)
    id = db.Column(db.Integer, primary_key=True)
    politico_id = db.Column(db.Integer, db.ForeignKey("politico.id"), nullable=False)
    sq_receita = db.Column(db.String(30))
    documento = db.Column(db.String(14))
    nome = db.Column(db.String(255))
    nome_norm = db.Column(db.String(255), index=True)
    origem = db.Column(db.String(100))
    valor = db.Column(Dinheiro)
    data = db.Column(db.Date)
    originario = db.Column(db.Boolean, default=False)

    politico = db.relationship("Politico", back_populates="doacoes")


class Emenda(db.Model):
    __tablename__ = "emenda"
    id = db.Column(db.Integer, primary_key=True)
    politico_id = db.Column(db.Integer, db.ForeignKey("politico.id"), nullable=False)
    codigo = db.Column(db.String(20), unique=True)
    ano = db.Column(db.Integer)
    tipo = db.Column(db.String(150))
    localidade = db.Column(db.String(150))
    funcao = db.Column(db.String(100))
    subfuncao = db.Column(db.String(100))
    valor_empenhado = db.Column(Dinheiro)
    valor_pago = db.Column(Dinheiro)

    politico = db.relationship("Politico", back_populates="emendas")


class Proposicao(db.Model):
    __tablename__ = "proposicao"
    __table_args__ = (db.UniqueConstraint("politico_id", "casa", "id_externo", name="uq_proposicao"),)
    id = db.Column(db.Integer, primary_key=True)
    politico_id = db.Column(db.Integer, db.ForeignKey("politico.id"), nullable=False)
    casa = db.Column(db.String(10))  # Câmara | Senado
    id_externo = db.Column(db.Integer)
    sigla_tipo = db.Column(db.String(10))
    numero = db.Column(db.Integer)
    ano = db.Column(db.Integer)
    ementa = db.Column(db.Text)
    data_apresentacao = db.Column(db.Date)
    url = db.Column(db.String(255))

    politico = db.relationship("Politico", back_populates="proposicoes")


class DespesaParlamentar(db.Model):
    __tablename__ = "despesa_parlamentar"
    __table_args__ = (db.UniqueConstraint("politico_id", "cod_documento", "valor", name="uq_despesa_parl"),)
    id = db.Column(db.Integer, primary_key=True)
    politico_id = db.Column(db.Integer, db.ForeignKey("politico.id"), nullable=False)
    ano = db.Column(db.Integer)
    mes = db.Column(db.Integer)
    tipo = db.Column(db.String(255))
    fornecedor_nome = db.Column(db.String(255))
    documento = db.Column(db.String(14), index=True)
    valor = db.Column(Dinheiro)
    url_documento = db.Column(db.String(255))
    cod_documento = db.Column(db.String(30))

    politico = db.relationship("Politico", back_populates="despesas")
