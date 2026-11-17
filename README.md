# Fiscal AI

Vigilância de gastos públicos da **Prefeitura de São Luís/MA**. O sistema coleta licitações, contratos e aditivos do PNCP, extratos do Diário Oficial do Município, sanções e convênios do Portal da Transparência e dados de CNPJ da Receita Federal. Depois aplica **nove verificações de risco** baseadas na Lei 14.133/2021 e mostra um painel público com ranking, evidências e links para as fontes.

A inteligência artificial (um modelo de linguagem **local**, via Ollama) **não decide** se há irregularidade. Ela só:
1. organiza os dados dos extratos do Diário Oficial;
2. avalia se a atividade da empresa (CNAE) combina com o objeto do contrato (regra de peso menor);
3. escreve, em português, a explicação dos indícios já calculados pelas regras.

> Os alertas indicam indícios de risco calculados automaticamente e não constituem acusação ou prova de irregularidade.

Trabalho de Conclusão de Curso.

---

## Pré-requisitos

| Ferramenta | Para quê |
|---|---|
| Python 3.11 ou mais novo | aplicação |
| XAMPP | **somente o MySQL/MariaDB** (o Apache do XAMPP não é usado) |
| MySQL Workbench | ver as tabelas e gerar o diagrama ER |
| Ollama + modelo `qwen2.5:7b` | extração e explicações (opcional para rodar o resto) |
| Chave da API do Portal da Transparência | sanções e convênios (gratuita) |

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # e preencha TRANSPARENCIA_API_KEY
```

1. Abra o XAMPP e clique em **Start** no MySQL.
2. No MySQL Workbench, conecte em `localhost:3306` (usuário `root`, sem senha) e rode:
   ```sql
   CREATE DATABASE fiscal_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. Crie as tabelas: `flask init-db` (também grava o DDL em `sql/schema.sql`).
4. Ollama: instale em <https://ollama.com>, depois `ollama pull qwen2.5:7b`. O modelo cabe numa GPU de 6 GB.
5. Chave do Portal da Transparência: cadastre-se em <https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email> e coloque a chave em `TRANSPARENCIA_API_KEY` no `.env`.

### Variáveis do `.env`

| Variável | Padrão |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:@localhost:3306/fiscal_ai?charset=utf8mb4` |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `qwen2.5:7b` |
| `TRANSPARENCIA_API_KEY` | vazio (sanções e convênios são pulados) |
| `COLETA_INICIO` | `2025-01-01` |
| `IBGE_MUNICIPIO` | `2111300` (São Luís) |

## Como usar

```bash
flask init-db
flask coletar --fonte pncp --de 2025-01-01 --ate 2025-03-31   # licitações, contratos, aditivos
flask coletar --fonte cnpj                                     # abertura, capital social, CNAE
flask coletar --fonte sancoes                                  # CEIS/CNEP (precisa da chave)
flask coletar --fonte convenios --de 2025-01-01 --ate 2025-03-31
flask coletar --fonte diario --de 2025-01-01 --ate 2025-03-31  # PDFs do Diário + extração via LLM
flask analisar                                                 # aplica as 9 regras e calcula o score
flask explicar --limite 30                                     # explicações em português (Ollama)
flask run                                                      # http://127.0.0.1:5000
```

`flask coletar` sem `--fonte` roda todas as fontes na ordem acima. Todos os comandos podem ser repetidos: os registros são atualizados, não duplicados. Edições do Diário baixadas sem o Ollama ficam pendentes e são processadas na próxima coleta.

Tempos de referência: o PNCP leva cerca de 3 minutos por mês de dados, e o Diário cerca de 30 segundos por edição (download do PDF).

## Arquitetura (MVC)

```
app/
  models/        M — tabelas (SQLAlchemy): orgao, fornecedor, contratacao, contrato, aditivo,
                     publicacao_diario, extrato_diario, sancao, alerta, convenio, coleta_log
  views/         V — templates Jinja2 (Bootstrap 5 + Chart.js) e filtros de formatação
  controllers/   C — rotas Flask: painel, contratos, fornecedores, metodologia
  services/
    coletores/   PNCP, Diário Oficial, Portal da Transparência, BrasilAPI
    regras/      uma classe por indicador de risco + config.py (pesos e limites)
    analisador.py   executa as regras, calcula score e nível
    llm.py          cliente do Ollama
  cli.py         comandos flask init-db / coletar / analisar / explicar
tests/           pytest (banco SQLite em memória, APIs e LLM simulados)
sql/schema.sql   DDL para o Workbench / monografia
```

### Diagrama ER no Workbench

*Database → Reverse Engineer…* → conexão local → schema `fiscal_ai` → *Execute*. O Workbench desenha o diagrama a partir das chaves estrangeiras.

## Verificações de risco

| Regra | Pontos | Base legal |
|---|---|---|
| Dispensa acima do limite legal | 25 | Lei 14.133/2021, art. 75 |
| Possível fracionamento de despesa | 20 | art. 75, §1º |
| Fornecedor recém-criado ou com capital baixo | 20 | art. 69 |
| Atividade (CNAE) incompatível com o objeto (LLM) | 10 | art. 67 |
| Fornecedor com sanção vigente (CEIS/CNEP) | 30 | art. 156; Lei 12.846/2013 |
| Concentração de contratos em um fornecedor | 15 | art. 5º |
| Baixa competição na licitação (aproximação) | 15 | art. 5º e 11 |
| Aditivos acima de 25% | 20 | art. 125 |
| Valor fora do padrão (TF-IDF + mediana) | 20 | art. 23 |

Score = soma dos pontos, até 100. **Baixo** < 30 ≤ **Médio** < 60 ≤ **Alto**. Pesos, limites e parâmetros ficam em `app/services/regras/config.py`. **Confira os limites de dispensa do decreto vigente** antes de cada ano.

## Testes

```bash
pytest
```

## Limitações conhecidas

- O PNCP publica só o vencedor de cada item, não o número de participantes. A regra de competição usa uma aproximação (licitações com vários itens vencidas por um único fornecedor).
- No PNCP, todas as secretarias aparecem sob o CNPJ do Município, por isso a comparação é por órgão contratante.
- Extratos do Diário Oficial nem sempre trazem o CNPJ. A ligação com o contrato usa o nome do fornecedor e o valor (±1%).
- A compatibilidade entre CNAE e objeto é um julgamento do modelo de linguagem e pode errar.
