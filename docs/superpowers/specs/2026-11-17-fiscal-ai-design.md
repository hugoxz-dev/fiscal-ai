# Fiscal AI — Design (TCC)

> Após aprovação, este documento será salvo em `docs/superpowers/specs/2026-11-17-fiscal-ai-design.md` no projeto, e o próximo passo é o plano de implementação (writing-plans).

## Contexto e porquê

TCC com prazo **< 2 meses**. O Fiscal AI vigia gastos da **Prefeitura de São Luís/MA (IBGE 2111300)**: coleta licitações/contratos, Diário Oficial Municipal e dados federais, aplica **indicadores de risco objetivos** e usa um **LLM local** para extrair dados de textos e explicar cada alerta em português. Sucesso = demo ponta a ponta funcionando na banca + metodologia defensável ("por que este contrato é suspeito?" sempre tem resposta rastreável).

## Objetivos
- Coletar dados reais de São Luís das 3 fontes + enriquecimento de CNPJ.
- Calcular score de risco (0–100) por contrato com regras auditáveis.
- Painel web público mostrando ranking, filtros e detalhe com evidências e explicação.

## Não-objetivos
- Outros municípios / Brasil inteiro (estrutura permite, mas não entra).
- Login, perfis de usuário, coleta agendada automática.
- Machine learning treinado / dados rotulados.

## Anti-objetivos (seria fracasso mesmo funcionando)
- LLM "decidir" sozinho que algo é suspeito — a decisão é sempre das regras.
- Alerta sem evidência rastreável (link para a fonte original).
- Linguagem acusatória: o sistema aponta **indícios de risco**, não fraude (aviso fixo no painel).

## Restrições (decididas)
- **Python + Flask**, arquitetura **MVC** explícita.
- **XAMPP só para o MySQL/MariaDB**; Flask serve as páginas (Apache do XAMPP não é usado — Python no Apache exigiria mod_wsgi). **MySQL Workbench** como cliente (ver tabelas, diagrama ER).
- **SQLAlchemy** (ORM) + driver **PyMySQL**.
- **Ollama local** com **qwen2.5:7b** (cabe na RTX 3050 6 GB do Lenovo LOQ-E, 16 GB RAM). Modelo configurável no `.env`.
- Painel **público, sem login**. Coleta/análise via **comandos manuais**.

## Abordagens consideradas
| | Abordagem | Trade-off | Decisão |
|---|---|---|---|
| A | Flask MVC + comandos CLI manuais + SQLAlchemy | MVC limpo, controle na demo, menos código | **Escolhida** |
| B | A + agendador (APScheduler) | Mais "produto", mais complexidade/risco no prazo | Descartada |
| C | A com SQL puro (mysql-connector) | SQL visível, muito código repetitivo | Descartada |

Papel da IA: **Regras + LLM explica** (escolhido) vs. ML de anomalias (difícil validar sem rótulos) vs. só-LLM (não reprodutível).

## Fontes de dados
| Fonte | Uso | Acesso |
|---|---|---|
| **PNCP API de Consultas** `pncp.gov.br/api/consulta/v1` | Contratações (`/contratacoes/publicacao?codigoMunicipioIbge=2111300&codigoModalidadeContratacao=N`, uma chamada por modalidade: 4,6,8,9…), contratos, termos aditivos | Pública, sem chave; datas `yyyyMMdd`, `tamanhoPagina` ≤ 50 |
| **Diário Oficial de São Luís** `diariooficial.saoluis.ma.gov.br` | Baixar PDFs das edições → texto (pdfplumber) → LLM extrai extratos de contrato/dispensa/aditivo | Público; scraping (requests + BeautifulSoup) |
| **Portal da Transparência API** | CEIS/CNEP (empresas sancionadas), transferências federais ao município | Chave gratuita (cadastro), header `chave-api-dados` |
| **BrasilAPI** `/api/cnpj/v1/{cnpj}` | Data de abertura, capital social, CNAE, situação do fornecedor | Pública, sem chave |

Período coletado por padrão: **01/2025 até hoje** (configurável) — *minha escolha*.

## Indicadores de risco (regras)
Cada regra é uma classe com `avaliar(contrato) -> Alerta | None`, peso configurável, e grava **evidência em JSON** (valores, datas, links).

1. **Dispensa acima do limite** — contratação direta (art. 75, Lei 14.133) com valor acima do limite vigente (valores atualizados por decreto; ficam no `config`).
2. **Fracionamento** — soma de dispensas do mesmo órgão para o mesmo fornecedor (ou objeto similar) no exercício > limite.
3. **Fornecedor recém-criado** — CNPJ aberto < 6 meses antes do contrato; ou capital social < 10% do valor contratado.
4. **CNAE incompatível** — LLM compara objeto do contrato com a atividade do CNAE (resposta sim/não + justificativa; peso menor por ser julgamento do LLM).
5. **Fornecedor sancionado** — CNPJ presente no CEIS/CNEP na data do contrato.
6. **Concentração** — fornecedor com > 30% do valor contratado por um órgão no ano.
7. **Competição baixa** — licitação com único participante/proposta. *Se o PNCP não expuser nº de participantes, usar proxy (item com um único resultado) e documentar a limitação.*
8. **Aditivos > 25%** — soma dos aditivos acima do limite legal sobre o valor original.
9. **Valor fora do padrão** — valor > 2× a mediana de contratos com objeto similar (agrupamento por TF-IDF do objeto); usa z-score em log(valor).

**Score** = soma dos pesos das regras disparadas, limitado a 100 → níveis **Baixo / Médio / Alto**. Thresholds e pesos em `config/regras.py`.

**LLM (Ollama)** só faz: (a) extrair campos estruturados dos textos do Diário (JSON validado), (b) regra 4, (c) gerar explicação em português a partir das evidências. Prompt nunca recebe a decisão para "julgar" — recebe os fatos e escreve o texto.

## Arquitetura (MVC)
```
fiscal_ai/
  app/
    __init__.py            # create_app(), registra blueprints e comandos CLI
    config.py              # lê .env (DB, chave Transparência, modelo Ollama, período)
    models/                # SQLAlchemy: orgao, fornecedor, contratacao, contrato,
                           #   aditivo, publicacao_diario, sancao, alerta, coleta_log
    controllers/           # blueprints Flask: painel, contratos, fornecedores, sobre/metodologia
    views/                 # templates Jinja2 + Bootstrap 5 + Chart.js
    services/
      coletores/           # pncp.py, diario_oficial.py, transparencia.py, brasilapi.py
      regras/              # base.py + uma classe por indicador
      analisador.py        # roda regras, calcula score, grava alertas
      llm.py               # cliente Ollama (HTTP localhost:11434), extração e explicação
    cli.py                 # flask coletar [--fonte] [--de --ate]; flask analisar; flask explicar
  tests/                   # pytest: regras com fixtures, parsers com JSON/PDF de exemplo
  sql/                     # dump do schema para Workbench/monografia
  .env.example  requirements.txt  README.md
```

## Telas do painel (público)
- **Início**: KPIs (contratos analisados, valor total, nº de alertas altos), gráfico por órgão, top 10 de maior risco.
- **Contratos**: tabela filtrável (órgão, modalidade, nível de risco, período, fornecedor), ordenável por score.
- **Detalhe do contrato**: dados, score, lista de indicadores disparados com evidência, explicação do LLM, links para PNCP/Diário.
- **Fornecedor**: dados do CNPJ, sanções, contratos e concentração.
- **Metodologia**: cada regra, base legal, pesos e o aviso "indícios ≠ fraude".

## Decisões deixadas ao implementador
- Detalhes do scraping do Diário (estrutura do HTML do site), cache de downloads.
- Nomes de colunas/índices, paginação, estilo visual.
- Tratamento de rate limit/retry nas APIs.

## Verificação
1. XAMPP: iniciar MySQL; `flask db` cria tabelas; conferir no Workbench.
2. `ollama pull qwen2.5:7b`; testar `services/llm.py`.
3. `flask coletar --de 2025-01-01 --ate 2025-01-31` → contar registros por tabela.
4. `flask analisar` → alertas gerados; `pytest` cobre cada regra com casos positivos e negativos.
5. `flask run` → abrir `http://127.0.0.1:5000`, navegar ranking → detalhe → link para a fonte original.
