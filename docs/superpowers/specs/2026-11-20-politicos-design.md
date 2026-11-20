# Fiscal AI — Políticos e ligações com fornecedores (design)

Data: 2026-11-20. Complementa `2026-11-17-fiscal-ai-design.md`.

## Intenção e porquê

O painel hoje é "de ler": ranking, alertas, detalhe. O usuário quer **mais interação**. O público imaginado é **jornalista, gente de prefeitura/controle interno e gente da política**: pessoas que procuram **ligações**. A função nova: digitar o nome de um político e ver o que liga essa pessoa a quem recebe dinheiro da Prefeitura de São Luís, além de dados básicos do mandato (bens, doadores, emendas, projetos, cota parlamentar).

Sucesso = na banca, digitar um nome, ver sugestões aparecerem, abrir a ficha e mostrar uma ligação rastreável até um contrato que o sistema já analisa.

## Objetivos

- Cadastro dos políticos **em exercício** ligados a São Luís: prefeito e vereadores de São Luís (eleição 2024), deputados federais e senadores do MA.
- Busca com **sugestões enquanto digita**.
- Ficha do político com: mandato, partido, bens declarados, doadores de campanha, **ligações com fornecedores da prefeitura**; para federais também emendas destinadas a São Luís, projetos de lei e cota parlamentar.
- Na página do fornecedor, o caminho inverso: "ligações com políticos".

## Não-objetivos

- Deputados estaduais (ALEMA não publica dados coletáveis).
- Suplentes de vereador que assumiram depois da eleição (o TSE só diz quem foi eleito). Fica registrado como limitação na Metodologia.
- Votações, presença, histórico de mandatos antigos, notícias.
- Outros municípios.

## Anti-objetivos (fracasso mesmo funcionando)

- **Ligação não é alerta.** Não entra no score, não vira regra, não entra na validação (decisão do usuário). É informação.
- Linguagem acusatória. Toda ficha mostra aviso: "ligação indica relação registrada em dados públicos, não irregularidade".
- **Expor CPF.** CPF de político, doador ou sócio nunca aparece na página nem na URL (rotas pelo id interno, como já é com fornecedor PF).
- Apresentar coincidência só de nome como certeza. Só é ligação quando nome **e** dígitos de CPF conferem (ver abaixo).

## Restrições

- Mesma pilha: Flask MVC, SQLAlchemy, MySQL do XAMPP, coleta por comando manual (`flask coletar --fonte ...`).
- Prazo do TCC (< 2 meses, validação dos alertas ainda pendente). O usuário decidiu **construir tudo de uma vez** (estimativa dele: ~2 dias), sem cortar emendas, projetos, cota nem Senado. Ainda assim a ordem do plano deve deixar o núcleo (TSE + sócios + ligações + busca + ficha) funcionando antes das fontes federais.
- Testes rodam em SQLite em memória (`tests/conftest.py`); busca sem acento não pode depender só da collation do MySQL.

## Abordagens consideradas

| | Abordagem | Trade-off | Decisão |
|---|---|---|---|
| 1 | Coletar antes e guardar no banco (novos coletores + tabelas) | Padrão do projeto, rápido, funciona offline na banca, cruzamento vira SQL; mais tabelas/coletores | **Escolhida pelo usuário** |
| 2 | Consultar as APIs ao vivo na busca | TSE só tem CSV (sem API), cruzamento com sócios inviável ao vivo, demo depende da internet | Descartada |
| 3 | Misto (TSE/sócios no banco, Câmara/Senado ao vivo com cache) | Menos tabelas, mas risco de rede na parte mais visível | Descartada |

Escopo de políticos: A (ligados a São Luís) escolhido, contra B (só federais, ficha rica mas desconectada da prefeitura) e C (todos, inclui estaduais — inviável no prazo).

## Fontes (conferidas em 2026-11-20)

| Fonte | Uso | Observações |
|---|---|---|
| **TSE dados abertos** `cdn.tse.jus.br/estatistica/sead/odsele/` | `consulta_cand/consulta_cand_{ano}.zip`, `bem_candidato/bem_candidato_{ano}.zip`, `prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip` | CSV `;`, latin-1, nulos como `#NULO`/`-1`. Zips nacionais com um CSV por UF. O de prestação de contas 2024 tem 1,35 GB, mas `receitas_candidatos_2024_MA.csv` tem 36 MB: **ler só o membro MA do zip remoto via HTTP Range** (testado, funciona; ZipFile sobre um leitor com Range). `NR_CPF_CNPJ_DOADOR` vem **completo**. Anos: 2024 (municipais), 2022 e 2018 (senadores eleitos em 2018). |
| **Câmara dos Deputados** `dadosabertos.camara.leg.br/api/v2` | `/deputados?siglaUf=MA` (18 em exercício), `/deputados/{id}` (CPF → liga ao TSE), `/deputados/{id}/despesas?ano=` (cota), `/proposicoes?idDeputadoAutor={id}` | Pública, JSON, paginada. |
| **Senado** `legis.senado.leg.br/dadosabertos` | `/senador/lista/atual.json` filtrando `UfParlamentar == "MA"` (3); projetos de autoria; cota (CEAPS, CSV anual da transparência do Senado) | Sem CPF: ligar ao TSE por nome completo + UF + cargo. Uma senadora atual (Ana Paula Lobato) é suplente e não tem prestação de contas própria. |
| **Portal da Transparência** `/api-de-dados/emendas?ano=&nomeAutor=` | Emendas de cada parlamentar do MA | Chave já configurada. Guardar só as com `localidadeDoGasto` de São Luís (ex.: começa com "SÃO LUÍS"); as com "MARANHÃO (UF)" não dá para atribuir ao município. |
| **BrasilAPI** (já usada) | Campo `qsa` = sócios do fornecedor | CPF do sócio vem mascarado: `***682847**` (6 dígitos do meio). Hoje o campo é ignorado. |

## Quem está em exercício

- Federais: listas atuais da Câmara e do Senado são a verdade; o TSE complementa (bens, doadores) quando o vínculo é encontrado.
- Municipais: TSE 2024, município São Luís, cargos Prefeito e Vereador, situação começando com "ELEITO" (`ELEITO`, `ELEITO POR QP`, `ELEITO POR MÉDIA`).

## Ligações (calculadas na consulta, não gravadas)

1. **Sócio de fornecedor doou ao político.** Doador PF cujo nome normalizado (sem acento, maiúsculo, espaços simples) é igual ao do sócio **e** cujo CPF, posições 4–9, é igual aos 6 dígitos visíveis do sócio.
2. **O próprio político é sócio de fornecedor.** Mesmo critério, com o CPF do político (TSE / Câmara).
3. **Fornecedor da prefeitura recebeu da cota parlamentar.** CNPJ/CPF da despesa = documento do fornecedor (vale para fornecedor PF também).
4. **Fornecedor pessoa física é o político ou um doador** *(decisão minha, após a revisão)*. Fornecedor PF guarda CPF completo, então compara CPF completo com o do político e com o dos doadores. É a ligação mais forte de todas.

**Quais receitas contam como doação** *(decisão minha)*: só as da eleição do mandato atual (2024 municipais; 2022 ou 2018 para cada senador; 2022 deputados). Entram doações diretas de pessoa física e, nas transferências de partido/outro candidato, o **doador originário** quando o TSE informa (`receitas_candidatos_doador_originario_{ano}_MA.csv`). Transferências sem doador originário aparecem na lista de doadores, mas não geram ligação. Suplente sem prestação própria (Ana Paula Lobato): a ficha diz "sem prestação de contas própria — assumiu como suplente" e não mostra os doadores do titular.

Cada ligação mostra o fornecedor, quantos contratos e valor total com a prefeitura, e o maior nível de alerta dele, com link para a página do fornecedor.

## Interface

- Menu: novo item **Políticos**.
- `/politicos`: campo de busca grande com sugestões enquanto digita (JS pequeno, sem framework, chamando `/politicos/busca.json?q=`), e abaixo a lista agrupada por cargo, com destaque para quem tem ligações.
- `/politicos/<id>`: ficha.

```
Fulano de Tal — Vereador (PXX) · São Luís · eleito 2024
Bens declarados: R$ 1,2 mi

Ligações com fornecedores da prefeitura (2)
  • Beltrano (sócio da Construtora ABC) doou R$ 10 mil
    → ABC: 4 contratos, R$ 3,1 mi · alerta médio
Doadores de campanha (37) ...........
Emendas para São Luís / Projetos / Cota parlamentar (só federais)
[aviso: ligação não é irregularidade]
```

- `fornecedor.html`: bloco "Ligações com políticos" quando houver.
- Metodologia: seção explicando as ligações, o critério de CPF parcial e as limitações (suplentes municipais, emendas sem município, senadores sem CPF).

## Dados (proposta)

- `politico`: nome, nome de urna, cpf (interno), cargo, partido, município/UF, ano da eleição, ids externos (TSE `SQ_CANDIDATO`, Câmara, Senado), foto, em_exercicio.
- `bem_declarado`, `doacao` (doador nome, documento, tipo, valor, data), `emenda`, `proposicao`, `despesa_parlamentar` (com CNPJ/CPF do favorecido).
- `socio` (fornecedor_id, nome, cpf mascarado, qualificação, data de entrada).

## Coleta

- Novas fontes no `FONTES` de `app/cli.py`: `tse`, `camara`, `senado`, `emendas`. Ordem em "todas": depois de `cnpj`, e `tse` antes de `camara`/`senado`/`emendas` (vínculos).
- O `cnpj` passa a gravar sócios. Fornecedores já enriquecidos precisam de nova passada (ex.: opção para refazer quem não tem sócios).
- Coletas idempotentes (rodar de novo não duplica), seguindo o padrão dos coletores atuais, com testes usando fixtures JSON/CSV em `tests/fixtures/`.

## Deixado para quem implementar

Nomes exatos de tabelas/colunas, como guardar o texto normalizado para busca sem acento, paginação das APIs, o período de cota e de projetos (sugestão: mandato atual), visual das páginas dentro do estilo atual (`fiscal.css`), e se a lista de doadores mostra todos ou os maiores.
