CREATE TABLE coleta_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	fonte VARCHAR(20) NOT NULL, 
	inicio DATETIME NOT NULL, 
	fim DATETIME, 
	registros INTEGER NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	erro TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE convenio (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	numero VARCHAR(30) NOT NULL, 
	orgao_concedente VARCHAR(255), 
	objeto TEXT, 
	valor NUMERIC(15, 2), 
	data_inicio DATE, 
	PRIMARY KEY (id), 
	UNIQUE (numero)
);

CREATE TABLE fornecedor (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	documento VARCHAR(14) NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	tipo VARCHAR(2) NOT NULL, 
	data_abertura DATE, 
	capital_social NUMERIC(15, 2), 
	cnae_codigo VARCHAR(10), 
	cnae_descricao VARCHAR(255), 
	cnaes_secundarios TEXT, 
	natureza_juridica VARCHAR(10), 
	situacao VARCHAR(50), 
	enriquecido_em DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (documento)
);

CREATE TABLE orgao (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	cnpj VARCHAR(14) NOT NULL, 
	razao_social VARCHAR(255) NOT NULL, 
	esfera VARCHAR(1), 
	PRIMARY KEY (id), 
	UNIQUE (cnpj)
);

CREATE TABLE publicacao_diario (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	data_edicao DATE, 
	numero_edicao VARCHAR(30), 
	url_pdf VARCHAR(500) NOT NULL, 
	texto LONGTEXT, 
	processado BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (url_pdf)
);

CREATE TABLE sancao (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	documento VARCHAR(14) NOT NULL, 
	cadastro VARCHAR(4) NOT NULL, 
	data_inicio DATE, 
	data_fim DATE, 
	orgao_sancionador VARCHAR(255), 
	descricao TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (documento, cadastro, data_inicio)
);

CREATE TABLE contratacao (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	numero_controle_pncp VARCHAR(60) NOT NULL, 
	orgao_id INTEGER NOT NULL, 
	ano INTEGER, 
	sequencial INTEGER, 
	modalidade_id INTEGER, 
	modalidade_nome VARCHAR(80), 
	amparo_legal VARCHAR(255), 
	objeto TEXT, 
	valor_estimado NUMERIC(15, 2), 
	valor_homologado NUMERIC(15, 2), 
	data_publicacao DATE, 
	qtd_fornecedores_resultado INTEGER, 
	link_pncp VARCHAR(255), 
	PRIMARY KEY (id), 
	UNIQUE (numero_controle_pncp), 
	FOREIGN KEY(orgao_id) REFERENCES orgao (id)
);

CREATE TABLE contrato (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	numero_controle_pncp VARCHAR(60) NOT NULL, 
	contratacao_id INTEGER, 
	orgao_id INTEGER NOT NULL, 
	fornecedor_id INTEGER NOT NULL, 
	ano INTEGER, 
	sequencial INTEGER, 
	objeto TEXT, 
	valor_inicial NUMERIC(15, 2), 
	valor_global NUMERIC(15, 2), 
	data_assinatura DATE, 
	modalidade_id INTEGER, 
	link_pncp VARCHAR(255), 
	score INTEGER NOT NULL, 
	nivel VARCHAR(10), 
	explicacao TEXT, 
	analisado_em DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (numero_controle_pncp), 
	FOREIGN KEY(contratacao_id) REFERENCES contratacao (id), 
	FOREIGN KEY(orgao_id) REFERENCES orgao (id), 
	FOREIGN KEY(fornecedor_id) REFERENCES fornecedor (id)
);

CREATE TABLE aditivo (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	contrato_id INTEGER NOT NULL, 
	numero VARCHAR(30) NOT NULL, 
	valor_acrescimo NUMERIC(15, 2) NOT NULL, 
	data DATE, 
	origem VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (contrato_id, numero, origem), 
	FOREIGN KEY(contrato_id) REFERENCES contrato (id)
);

CREATE TABLE alerta (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	contrato_id INTEGER NOT NULL, 
	regra_codigo VARCHAR(30) NOT NULL, 
	pontos INTEGER NOT NULL, 
	evidencia JSON NOT NULL, 
	criado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contrato_id) REFERENCES contrato (id)
);

CREATE TABLE extrato_diario (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	publicacao_id INTEGER NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	documento_fornecedor VARCHAR(14), 
	nome_fornecedor VARCHAR(255), 
	valor NUMERIC(15, 2), 
	objeto TEXT, 
	trecho TEXT, 
	contrato_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(publicacao_id) REFERENCES publicacao_diario (id), 
	FOREIGN KEY(contrato_id) REFERENCES contrato (id)
);

CREATE TABLE julgamento_cnae (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	contrato_id INTEGER NOT NULL, 
	cnae_descricao TEXT NOT NULL, 
	objeto TEXT, 
	modelo VARCHAR(60), 
	compativel BOOL NOT NULL, 
	justificativa TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (contrato_id), 
	FOREIGN KEY(contrato_id) REFERENCES contrato (id)
);
