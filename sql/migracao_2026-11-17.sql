-- Atualiza um banco criado antes da revisão final (17/11/2026). Banco novo: use só `flask init-db`.
-- Depois de rodar: flask coletar --fonte cnpj; flask coletar --fonte pncp --de ... --ate ...; flask analisar
ALTER TABLE fornecedor ADD COLUMN cnaes_secundarios TEXT NULL;
ALTER TABLE fornecedor ADD COLUMN natureza_juridica VARCHAR(10) NULL;
ALTER TABLE contratacao ADD COLUMN amparo_legal VARCHAR(255) NULL;
ALTER TABLE julgamento_cnae MODIFY cnae_descricao TEXT NOT NULL;
ALTER TABLE julgamento_cnae ADD COLUMN objeto TEXT NULL;
DELETE FROM aditivo WHERE origem = 'diario';
UPDATE extrato_diario SET contrato_id = NULL WHERE tipo = 'aditivo';
UPDATE fornecedor SET enriquecido_em = NULL WHERE tipo = 'PJ';
