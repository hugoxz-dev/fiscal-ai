-- Monetização: data em que o contrato entrou no banco (base das "novidades" do monitoramento).
ALTER TABLE contrato ADD COLUMN coletado_em DATETIME NULL;
UPDATE contrato SET coletado_em = NOW() WHERE coletado_em IS NULL;
ALTER TABLE contrato MODIFY coletado_em DATETIME NOT NULL;
-- As tabelas novas (usuario, assinatura, seguido, chave_api, uso_api, pedido_institucional)
-- são criadas por `flask init-db`, que só cria o que ainda não existe.
