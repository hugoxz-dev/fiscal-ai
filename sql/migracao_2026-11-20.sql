-- cod_documento da cota parlamentar passa de 30 para 40 caracteres (a Câmara usa UUID de 36).
ALTER TABLE despesa_parlamentar MODIFY cod_documento VARCHAR(40) NULL;
