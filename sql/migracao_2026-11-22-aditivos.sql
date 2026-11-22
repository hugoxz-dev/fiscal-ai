-- Regra de aditivos: valor global do contrato após cada termo (o PNCP de São Luís informa nele o novo
-- valor total, e o mesmo número vem no campo de acréscimo). Depois, rebuscar os termos dos contratos com aditivo.
ALTER TABLE aditivo ADD COLUMN valor_global NUMERIC(15, 2) NULL AFTER valor_acrescimo;
-- Texto do termo (objeto e observação): costuma declarar o percentual de acréscimo, usado pela regra.
ALTER TABLE aditivo ADD COLUMN descricao TEXT NULL AFTER valor_global;
