# Políticos e ligações com fornecedores — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Busca de políticos ligados a São Luís (prefeito, vereadores, deputados federais e senadores do MA) com ficha que mostra ligações com fornecedores da prefeitura, bens, doadores, emendas, projetos e cota parlamentar.

**Architecture:** Novos coletores (padrão de `app/services/coletores/`) gravam tabelas novas no MySQL via `flask coletar --fonte ...`. As ligações são calculadas na consulta por um serviço (`app/services/ligacoes.py`), nunca gravadas nem pontuadas. Novo blueprint `politicos` com busca por sugestão (JSON + JS puro) e ficha.

**Tech Stack:** Python 3.11, Flask 3.1, SQLAlchemy 2.0, MySQL (XAMPP), requests, pytest com SQLite em memória. Sem dependências novas.

**Spec:** `docs/superpowers/specs/2026-11-20-politicos-design.md`

## Global Constraints

- Ligação **não é alerta**: nada aqui toca `Alerta`, `score`, regras ou validação.
- **CPF nunca aparece** em HTML, JSON ou URL (político, doador, sócio). Rotas pelo id interno.
- Ligação confirmada só quando nome normalizado **e** dígitos de CPF conferem. Coincidência só de nome aparece em seção separada com o rótulo exato: `nome igual — CPF não disponível para confirmar`.
- Aviso fixo na ficha e no bloco do fornecedor, texto exato: `Ligação indica relação registrada em dados públicos, não irregularidade.`
- Doações: só da eleição do mandato atual (2024 municipais; 2022 deputados; 2022 ou 2018 senadores).
- Emendas: só com `localidadeDoGasto` que, normalizada, começa com `SAO LUIS`.
- Coletas idempotentes: rodar de novo não duplica.
- Textos de interface em português, no estilo atual (`fiscal.css`, `base.html`).
- Arquivos `.py` em LF. Não commitar as alterações visuais pendentes do usuário (`fiscal.css`, `base.html`, `inicio.html`, `_enfeite.html`, `static/vendor/`) a não ser as linhas que este plano muda; usar `git add -p` em `base.html`.

## Fatos das fontes (conferidos em 2026-11-20)

- TSE: `https://cdn.tse.jus.br/estatistica/sead/odsele/{consulta_cand|bem_candidato|prestacao_contas}/...zip`, CSV `;`, latin-1, aspas, nulos `#NULO`, `#NULO#`, `-1`, `-4`. Membros por UF: `consulta_cand_{ano}_MA.csv`, `bem_candidato_{ano}_MA.csv`, `receitas_candidatos_{ano}_MA.csv`, `receitas_candidatos_doador_originario_{ano}_MA.csv` (zip de contas: `prestacao_de_contas_eleitorais_candidatos_{ano}.zip`).
- **2024: `NR_CPF_CANDIDATO` = `-4` (não divulgado). 2022/2018: CPF completo.** `NR_CPF_CNPJ_DOADOR` completo.
- Colunas usadas — consulta_cand: `SQ_CANDIDATO, NM_CANDIDATO, NM_URNA_CANDIDATO, NR_CPF_CANDIDATO, DS_CARGO, SG_PARTIDO, NM_UE, SG_UF, DS_SIT_TOT_TURNO, ANO_ELEICAO`. bem: `SQ_CANDIDATO, DS_TIPO_BEM_CANDIDATO, DS_BEM_CANDIDATO, VR_BEM_CANDIDATO`. receitas: `SQ_PRESTADOR_CONTAS, SQ_CANDIDATO, NR_CPF_CNPJ_DOADOR, NM_DOADOR, DS_ORIGEM_RECEITA, SQ_RECEITA, DT_RECEITA, VR_RECEITA`. originário: `SQ_PRESTADOR_CONTAS, NR_CPF_CNPJ_DOADOR_ORIGINARIO, NM_DOADOR_ORIGINARIO, SQ_RECEITA, DT_RECEITA, VR_RECEITA`. Ler por nome de coluna (2018 pode ter colunas a mais/menos).
- BrasilAPI `qsa[]`: `nome_socio`, `cnpj_cpf_do_socio` (`***682847**` para PF; 14 dígitos para sócio PJ), `qualificacao_socio`, `data_entrada_sociedade`.
- Câmara `https://dadosabertos.camara.leg.br/api/v2`: `/deputados?siglaUf=MA&itens=100` (18), `/deputados/{id}` → `dados.cpf`, `dados.nomeCivil`, `dados.ultimoStatus.{nome,siglaPartido,urlFoto}`; `/deputados/{id}/despesas?ano=&itens=100&pagina=` → `ano, mes, tipoDespesa, codDocumento, nomeFornecedor, cnpjCpfFornecedor, valorLiquido, urlDocumento`; `/proposicoes?idDeputadoAutor=&siglaTipo=PL,PLP,PEC&dataApresentacaoInicio=AAAA-MM-DD&itens=100&pagina=` → `id, siglaTipo, numero, ano, ementa, dataApresentacao`.
- Senado: `https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json` → `ListaParlamentarEmExercicio.Parlamentares.Parlamentar[].IdentificacaoParlamentar.{CodigoParlamentar, NomeParlamentar, NomeCompletoParlamentar, SiglaPartidoParlamentar, UfParlamentar, UrlFotoParlamentar}`; `/dadosabertos/processo?codigoParlamentarAutor={id}&sigla={PL|PLP|PEC}` (header `Accept: application/json`) → `[{codigoMateria, identificacao "PL 896/2023", ementa, dataApresentacao}]`; CEAPS `https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv` (latin-1, `;`, 1ª linha `"ULTIMA ATUALIZACAO";...` antes do cabeçalho `ANO;MES;SENADOR;TIPO_DESPESA;CNPJ_CPF;FORNECEDOR;DOCUMENTO;DATA;DETALHAMENTO;VALOR_REEMBOLSADO;COD_DOCUMENTO`; `SENADOR` = nome parlamentar em maiúsculas; valor `399,44`).
- Portal da Transparência `/api-de-dados/emendas?ano=&nomeAutor=&pagina=` → `codigoEmenda, ano, tipoEmenda, nomeAutor, localidadeDoGasto, funcao, subfuncao, valorEmpenhado "893.200,00", valorPago`.

## Review Focus

1. **Ficha de político sem dados** (federal sem vínculo no TSE, suplente, sem emendas) → página abre com mensagens, nunca 500. Teste em Task 5.
2. **Busca com acento, maiúsculas, 1 caractere ou vazia** → `sao luis` e `SÃO` acham "São Luís"; `q` com menos de 2 caracteres devolve `[]`. Teste em Task 5.
3. **Homônimo**: doador com mesmo nome do sócio mas CPF do meio diferente não vira ligação; sócio PJ (14 dígitos) não casa com doador. Teste em Task 4.
4. **CPF vazando**: CPF do político, do doador e o documento de fornecedor PF não aparecem no HTML da ficha nem no JSON da busca. Teste em Task 5.
5. **Rodar a coleta duas vezes** não duplica políticos, doações, bens, sócios, despesas, projetos ou emendas. Testes em cada coletor.

---

### Task 1: Modelos novos e normalização de texto

**Files:**
- Create: `app/services/texto.py`, `app/models/politico.py`, `app/models/socio.py`
- Modify: `app/models/__init__.py`, `app/services/coletores/transparencia.py` (trocar `_sem_acento` por `texto.normalizar`)
- Test: `tests/test_texto.py`, `tests/test_models.py` (acrescentar)

**Interfaces:**
- Produces:
  - `texto.normalizar(s: str | None) -> str` — sem acento, maiúsculo, espaços colapsados, sem pontas; `None` → `""`.
  - `texto.digitos(s: str | None) -> str`.
  - `texto.cpf_meio(doc: str | None) -> str | None` — CPF de 11 dígitos → `doc[3:9]`; máscara `***682847**` → `"682847"`; qualquer outra coisa → `None`.
  - `texto.cpf_valido(s) -> str | None` — 11 dígitos ou `None` (descarta `-4`, `#NULO`).
  - `texto.dinheiro_br(s: str | None) -> Decimal | None` — `"893.200,00"` → `Decimal("893200.00")`, `"800,00"`; aceita float/int (Câmara).
  - Modelos (todos com `id` inteiro):
    - `Politico` (`politico`): `nome` String(255) not null, `nome_urna` String(255), `nome_busca` String(600) index (normalizado de `nome + nome_urna + partido + cargo`, preenchido por `Politico.atualizar_busca()`), `cpf` String(11) null, `cargo` String(20) (`"Prefeito" | "Vereador" | "Deputado Federal" | "Senador"`), `partido` String(30), `uf` String(2), `municipio` String(100) null, `ano_eleicao` Integer null, `sq_candidato` String(20) unique null, `id_camara` Integer unique null, `id_senado` Integer unique null, `foto_url` String(255), `em_exercicio` Boolean default True. Relationships: `bens`, `doacoes`, `emendas`, `proposicoes`, `despesas` (cascade delete-orphan).
    - `BemDeclarado` (`bem_declarado`): `politico_id` FK, `tipo` String(255), `descricao` Text, `valor` Dinheiro.
    - `Doacao` (`doacao`): `politico_id` FK, `sq_receita` String(30), `documento` String(14) (dígitos do doador), `nome` String(255), `nome_norm` String(255) index, `origem` String(100), `valor` Dinheiro, `data` Date, `originario` Boolean default False. Unique (`politico_id`, `sq_receita`, `originario`, `documento`).
    - `Emenda` (`emenda`): `politico_id` FK, `codigo` String(20) unique, `ano` Integer, `tipo` String(150), `localidade` String(150), `funcao` String(100), `subfuncao` String(100), `valor_empenhado` Dinheiro, `valor_pago` Dinheiro.
    - `Proposicao` (`proposicao`): `politico_id` FK, `casa` String(10) (`"Câmara" | "Senado"`), `id_externo` Integer, `sigla_tipo` String(10), `numero` Integer, `ano` Integer, `ementa` Text, `data_apresentacao` Date, `url` String(255). Unique (`politico_id`, `casa`, `id_externo`).
    - `DespesaParlamentar` (`despesa_parlamentar`): `politico_id` FK, `ano` Integer, `mes` Integer, `tipo` String(255), `fornecedor_nome` String(255), `documento` String(14) index (dígitos), `valor` Dinheiro, `url_documento` String(255), `cod_documento` String(30). Unique (`politico_id`, `cod_documento`, `valor`).
    - `Socio` (`socio`, em `socio.py`): `fornecedor_id` FK, `nome` String(255), `nome_norm` String(255) index, `cpf_meio` String(6) null index, `qualificacao` String(100), `data_entrada` Date. Unique (`fornecedor_id`, `nome`). `Fornecedor.socios` relationship (back_populates).
  - Todos exportados em `app/models/__init__.py` e `__all__`.

- [ ] **Step 1: Write the failing tests** — `tests/test_texto.py`:

```python
def test_normalizar():
    assert normalizar("  São  Luís ") == "SAO LUIS"
    assert normalizar(None) == ""

def test_cpf_meio():
    assert cpf_meio("12368284799") == "682847"
    assert cpf_meio("***682847**") == "682847"
    assert cpf_meio("12345678000199") is None and cpf_meio("-4") is None and cpf_meio(None) is None

def test_cpf_valido():
    assert cpf_valido("02898953407") == "02898953407"
    assert cpf_valido("-4") is None and cpf_valido("#NULO") is None

def test_dinheiro_br():
    assert dinheiro_br("893.200,00") == Decimal("893200.00")
    assert dinheiro_br("800,00") == Decimal("800.00")
    assert dinheiro_br(-419.94) == Decimal("-419.94")
    assert dinheiro_br("") is None and dinheiro_br("#NULO") is None
```

E em `tests/test_models.py`: `test_politico_busca_e_relacoes` — cria `Politico(nome="Fulano de Tál", nome_urna="Fulaninho", partido="PXX", cargo="Vereador")`, chama `atualizar_busca()`, confere `nome_busca == "FULANO DE TAL FULANINHO PXX VEREADOR"`; adiciona um `BemDeclarado` e uma `Doacao`, commit, e confere `len(p.bens) == 1`. `test_socio_do_fornecedor` — `Fornecedor` com um `Socio`, confere `f.socios[0].cpf_meio`.

- [ ] **Step 2: Run** `pytest tests/test_texto.py tests/test_models.py -v` — Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `texto.py`, os modelos e o export; em `transparencia.py` substituir `_sem_acento(x)` por `normalizar(x)` (o teste existente de convênio continua passando).
- [ ] **Step 4: Run** `pytest -q` — Expected: tudo PASS.
- [ ] **Step 5: Commit** `feat: modelos de políticos, doações, sócios e normalização de texto`

---

### Task 2: Sócios dos fornecedores (BrasilAPI)

**Files:**
- Modify: `app/services/coletores/brasilapi.py`, `app/cli.py`
- Modify: `tests/fixtures/brasilapi_cnpj.json` (acrescentar `qsa` com um sócio PF `***682847**` e um sócio PJ de 14 dígitos)
- Test: `tests/test_brasilapi.py`

**Interfaces:**
- Consumes: `Socio`, `texto.normalizar`, `texto.cpf_meio`.
- Produces:
  - `parse_socios(d: dict) -> list[dict]` (chaves = colunas de `Socio` exceto `fornecedor_id`).
  - `gravar_socios(f: Fornecedor, socios: list[dict]) -> int` — substitui os sócios do fornecedor (apaga e insere); retorna quantos.
  - `enriquecer_fornecedores(...)` passa a chamar `gravar_socios` também.
  - `coletar_socios(get: Callable | None = None, pausa: float = 0.5) -> int` — para fornecedores PJ já enriquecidos (`enriquecido_em` não nulo) **sem nenhum** `Socio`; retorna nº de fornecedores com sócios gravados.
  - CLI: fonte `socios` em `FONTES`, logo depois de `cnpj`.

- [ ] **Step 1: Write the failing tests**: `test_parse_socios` (sócio PF → `cpf_meio == "682847"`, `nome_norm` normalizado, `data_entrada` date; sócio PJ → `cpf_meio is None`); `test_enriquecer_grava_socios` (após `enriquecer_fornecedores`, `Socio.query.count() == 2`); `test_coletar_socios_so_quem_falta_e_idempotente` (fornecedor já enriquecido sem sócios é consultado; segunda chamada não consulta nem duplica — `get` falso conta chamadas); `test_parse_cnpj` existente continua passando.
- [ ] **Step 2: Run** `pytest tests/test_brasilapi.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** as funções e registre `_coletar_socios` em `FONTES` (help do `--fonte` lista as novas fontes).
- [ ] **Step 4: Run** `pytest tests/test_brasilapi.py tests/test_cli.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: grava sócios dos fornecedores (QSA da BrasilAPI)`

---

### Task 3: Coletor do TSE (leitura parcial do zip remoto)

**Files:**
- Create: `app/services/coletores/zip_remoto.py`, `app/services/coletores/tse.py`
- Create: `tests/fixtures/tse/` com `consulta_cand_2024_MA.csv`, `consulta_cand_2022_MA.csv`, `bem_candidato_2024_MA.csv`, `receitas_candidatos_2024_MA.csv`, `receitas_candidatos_doador_originario_2024_MA.csv` (poucas linhas cada, gravados em **latin-1**, com as colunas reais listadas em "Fatos das fontes" + colunas extras irrelevantes)
- Modify: `app/cli.py`
- Test: `tests/test_zip_remoto.py`, `tests/test_tse.py`

**Interfaces:**
- Consumes: modelos da Task 1, `texto.*`.
- Produces:
  - `zip_remoto.LeitorIntervalo(tamanho: int, baixar: Callable[[int, int], bytes])` — `io.RawIOBase` seekable cujo `readinto` pede `baixar(inicio, fim_inclusivo)`.
  - `zip_remoto.abrir_membro(url: str, membro: str) -> TextIO` — HEAD para o tamanho, `zipfile.ZipFile(io.BufferedReader(LeitorIntervalo(...), 1 << 20))`, devolve o membro decodificado em latin-1. Usa `criar_sessao()`.
  - `tse.ler_csv(arquivo: TextIO) -> Iterator[dict]` — `csv.DictReader(delimiter=";")`, valores `#NULO`, `#NULO#`, `#NE`, `-1`, `-3`, `-4` viram `None`.
  - `tse.coletar_tse(abrir: Callable[[str, str], TextIO] | None = None) -> int` — retorna nº de doações gravadas. Passos, nesta ordem:
    1. `consulta_cand_2024_MA.csv`: `normalizar(NM_UE) == "SAO LUIS"`, `DS_CARGO` em `PREFEITO`/`VEREADOR`, `DS_SIT_TOT_TURNO` começando com `ELEITO` → upsert `Politico` por `sq_candidato` (`cargo` "Prefeito"/"Vereador", `municipio="São Luís"`, `uf="MA"`, `ano_eleicao=2024`, `cpf=cpf_valido(...)`).
    2. Para cada `Politico` com `id_camara` ou `id_senado` e sem `sq_candidato`: procura em `consulta_cand_2022_MA.csv` e depois `consulta_cand_2018_MA.csv`, cargo `DEPUTADO FEDERAL`/`SENADOR` conforme o cargo, situação começando com `ELEITO`; casa por CPF quando o político tem CPF, senão por `normalizar(NM_CANDIDATO) == normalizar(politico.nome)`. Preenche `sq_candidato`, `ano_eleicao` e `cpf` (se vazio e válido).
    3. Para cada ano com políticos vinculados: `bem_candidato_{ano}_MA.csv` → substitui os bens do político.
    4. `receitas_candidatos_{ano}_MA.csv` → upsert `Doacao(originario=False)`; guarda `SQ_PRESTADOR_CONTAS → politico`. Depois `receitas_candidatos_doador_originario_{ano}_MA.csv` → `Doacao(originario=True)` para prestadores conhecidos.
  - URLs: `BASE_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele"`; zips `consulta_cand/consulta_cand_{ano}.zip`, `bem_candidato/bem_candidato_{ano}.zip`, `prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip`.
  - CLI: fonte `tse` em `FONTES`, depois de `senado` (Task 8 adiciona `camara` e `senado` antes dela; até lá fica no fim). A dependência é: TSE vincula federais já criados por Câmara/Senado.

- [ ] **Step 1: Write the failing tests**:
  - `test_leitor_intervalo_le_membro_de_zip`: monta um zip em memória com `a_MA.csv` e `b.csv`, `LeitorIntervalo(len(dados), lambda i, f: dados[i:f+1])`, `zipfile` lê `a_MA.csv` correto e o número de chamadas de `baixar` é menor que o necessário para baixar tudo byte a byte (sanidade: só lê o que precisa).
  - `test_ler_csv_nulos_e_latin1`: `#NULO` e `-4` → `None`; acento lido certo.
  - `test_coletar_tse_municipais`: `abrir` falso lê de `tests/fixtures/tse/`; fixture tem 1 prefeito eleito, 2 vereadores eleitos, 1 suplente e 1 vereador de outro município → 3 políticos, `cpf is None` (vem `-4`).
  - `test_coletar_tse_vincula_federal_por_cpf_e_por_nome`: pré-cria um deputado (`id_camara=1`, `cpf` do fixture) e um senador (`id_senado=2`, sem CPF, nome do fixture com acento diferente) → ambos recebem `sq_candidato` e `ano_eleicao=2022`.
  - `test_coletar_tse_doacoes_e_originario`: doações diretas e originárias gravadas, `valor` Decimal, `data` date, `documento` 11 dígitos.
  - `test_coletar_tse_idempotente`: duas execuções → mesmas contagens de `Politico`, `Doacao`, `BemDeclarado`.
- [ ] **Step 2: Run** `pytest tests/test_zip_remoto.py tests/test_tse.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `zip_remoto.py`, `tse.py`, registrar `_coletar_tse`.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Verificação manual (rede):** `python -c` que chama `abrir_membro` no zip de contas 2024 e lê a 1ª linha de `receitas_candidatos_2024_MA.csv` — Expected: cabeçalho começando com `"DT_GERACAO"` em poucos segundos (não baixa 1,35 GB).
- [ ] **Step 6: Commit** `feat: coletor do TSE (eleitos, bens e doações) lendo só o Maranhão do zip remoto`

---

### Task 4: Serviço de ligações

**Files:**
- Create: `app/services/ligacoes.py`
- Test: `tests/test_ligacoes.py`

**Interfaces:**
- Consumes: modelos da Task 1, `Contrato` (`score`, `nivel`, `valor_global`, `fornecedor_id`).
- Produces:
  - `@dataclass Ligacao`: `tipo: str` (`"socio_doou" | "politico_socio" | "fornecedor_pf" | "cota"`), `confirmada: bool` (True = CPF conferiu), `politico: Politico`, `fornecedor: Fornecedor`, `pessoa: str` (nome de quem liga), `valor: Decimal | None` (doação ou soma da cota), `descricao: str` (frase pronta, ex.: `"Beltrano, sócio de Construtora ABC, doou R$ 10.000,00"`; usar `_filtros.moeda`).
  - `resumo_fornecedor(f: Fornecedor) -> dict` → `{"contratos": int, "total": Decimal, "nivel": str | None}` (maior nível entre os contratos: Alto > Médio > Baixo).
  - `ligacoes_do_politico(p: Politico) -> list[Ligacao]` — ordem: confirmadas antes, depois por valor desc.
  - `ligacoes_do_fornecedor(f: Fornecedor) -> list[Ligacao]`.
  - `contar_ligacoes() -> dict[int, int]` — `politico_id → nº de ligações confirmadas` (para a lista).
- Regras (critério exato):
  - `socio_doou`: `Doacao.documento` com 11 dígitos, `doacao.nome_norm == socio.nome_norm` **e** `cpf_meio(doacao.documento) == socio.cpf_meio`. Sempre confirmada. Várias doações da mesma pessoa ao mesmo político → uma ligação com a soma.
  - `politico_socio`: com `p.cpf` → `normalizar(p.nome) == socio.nome_norm` e `cpf_meio(p.cpf) == socio.cpf_meio` (confirmada); sem `p.cpf` → só nome (`confirmada=False`).
  - `fornecedor_pf`: fornecedor `tipo == "PF"`; `documento == p.cpf` (confirmada) ou `documento == doacao.documento` de um doador do político (confirmada); sem `p.cpf` → `normalizar(f.nome) == normalizar(p.nome)` (`confirmada=False`).
  - `cota`: `DespesaParlamentar.documento == Fornecedor.documento`; soma por (político, fornecedor). Confirmada.
- Implementação: carregar em Python (volumes pequenos), indexando sócios por `(nome_norm, cpf_meio)` e por `nome_norm`. Nenhum campo de `Ligacao` contém CPF.

- [ ] **Step 1: Write the failing tests** (fábricas locais criando fornecedor, sócio, político, doação, despesa, contrato com `nivel`):
  - `test_socio_doou_confirma_por_nome_e_cpf` — 1 ligação, `confirmada`, `valor` = soma de 2 doações.
  - `test_homonimo_com_cpf_diferente_nao_liga` — mesmo nome, meio diferente → `[]`.
  - `test_socio_pj_nao_liga` — sócio com `cpf_meio=None` e doador de mesmo nome → `[]`.
  - `test_politico_socio_sem_cpf_vira_nao_confirmada` — vereador sem CPF, sócio com mesmo nome → `confirmada is False`.
  - `test_fornecedor_pf_e_o_politico` — federal com CPF igual ao documento do fornecedor PF → confirmada.
  - `test_cota_soma_por_fornecedor` — duas despesas → uma ligação com a soma.
  - `test_ligacoes_do_fornecedor_e_resumo` — `resumo_fornecedor` com contratos `Médio` e `Baixo` → `nivel == "Médio"`, `contratos == 2`.
  - `test_descricao_sem_cpf` — nenhum CPF de entrada aparece em `descricao`.
- [ ] **Step 2: Run** `pytest tests/test_ligacoes.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `ligacoes.py`.
- [ ] **Step 4: Run** `pytest tests/test_ligacoes.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: serviço de ligações entre políticos e fornecedores`

---

### Task 5: Páginas de políticos (busca com sugestões e ficha)

**Files:**
- Create: `app/controllers/politicos.py`, `app/views/politicos.html`, `app/views/politico.html`, `app/static/politicos.js`
- Modify: `app/__init__.py` (registrar blueprint), `app/views/base.html` (item **Políticos** no `<nav>`, entre Contratos e Metodologia, ativo quando `atual.startswith('politicos')`), `app/static/fiscal.css` (só o necessário para a caixa de sugestões)
- Test: `tests/test_politicos_views.py`

**Interfaces:**
- Consumes: `ligacoes_do_politico`, `resumo_fornecedor`, `contar_ligacoes` (Task 4).
- Produces: blueprint `politicos` com:
  - `GET /politicos` → `politicos.lista`: busca + lista agrupada na ordem Prefeito, Senador, Deputado Federal, Vereador, só `em_exercicio`; cada item mostra nome de urna, partido e um selo com o nº de ligações confirmadas quando > 0.
  - `GET /politicos/busca.json?q=` → `politicos.busca`: `q` normalizado; menos de 2 caracteres → `[]`; senão até 10 de `Politico.nome_busca LIKE %q%` (só `em_exercicio`) → `[{"id", "nome", "nome_urna", "cargo", "partido", "url"}]`.
  - `GET /politicos/<int:id>` → `politicos.detalhe`: 404 se não existe. Contexto: `p`, `ligacoes` (separadas em `confirmadas` e `so_nome`), `total_bens`, `bens`, `doadores` (agregado por nome: soma e qtd, desc, top 50, e o total geral), `emendas`, `proposicoes` (mais recentes primeiro), `cota` (soma por `tipo`, desc, e total).
- Ficha (conforme o esboço do spec): cabeçalho `nome_urna — cargo (partido) · município/UF · eleito {ano}`; "Ligações com fornecedores da prefeitura" com link para `fornecedores.detalhe` e o resumo (contratos, total, nível); seção separada com o rótulo `nome igual — CPF não disponível para confirmar` quando houver; aviso fixo da Global Constraints; sem `sq_candidato` → `Não encontramos prestação de contas no TSE para este mandato (por exemplo, quem assumiu como suplente).`; seções Emendas para São Luís / Projetos / Cota parlamentar só para Deputado Federal e Senador, com mensagem quando vazias.
- `politicos.js`: no `input` com debounce de 200 ms, `fetch` em `busca.json`, mostra lista de sugestões navegável por setas/Enter, link para a ficha; sem JS, o formulário faz GET em `/politicos?q=` e a lista filtra no servidor pelo mesmo critério.

- [ ] **Step 1: Write the failing tests**:
  - `test_busca_sem_acento_e_minimo` — político "São Luís Teste"; `q=sao luis` e `q=SÃO` acham; `q=s` e `q=` → `[]`.
  - `test_busca_nao_vaza_cpf` — político com `cpf="12345678901"`; o corpo de `busca.json` não contém `12345678901`.
  - `test_ficha_sem_dados_abre` — senador sem `sq_candidato`, sem nada ligado → 200 e contém a frase de prestação de contas.
  - `test_ficha_mostra_ligacao_e_aviso_sem_cpf` — cenário de `socio_doou` → contém nome do fornecedor, o aviso exato, e não contém o CPF do doador nem do político.
  - `test_ficha_so_nome_em_secao_separada` — vereador sem CPF → contém `nome igual — CPF não disponível para confirmar`.
  - `test_lista_agrupada_e_menu` — `/politicos` 200, contém "Vereador" e o link do menu.
  - `test_ficha_404`.
- [ ] **Step 2: Run** `pytest tests/test_politicos_views.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** controller, templates, JS, nav e CSS.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Ver no navegador** (`flask run`, `/politicos`): digitar 2 letras mostra sugestões; Enter abre a ficha.
- [ ] **Step 6: Commit** (com `git add -p app/views/base.html app/static/fiscal.css`, só as linhas desta task) `feat: busca de políticos com sugestões e ficha com ligações`

---

### Task 6: Ligações na página do fornecedor e Metodologia

**Files:**
- Modify: `app/controllers/fornecedores.py`, `app/views/fornecedor.html`, `app/views/metodologia.html`
- Test: `tests/test_contratos_views.py` (ou o teste de fornecedor existente), `tests/test_app.py`

**Interfaces:**
- Consumes: `ligacoes_do_fornecedor` (Task 4).
- Produces: bloco "Ligações com políticos" no fornecedor (só quando houver), com link para `politicos.detalhe`, aviso exato e separação confirmadas / só nome. Seção "Ligações com políticos" na Metodologia explicando: os 4 tipos, critério nome + 6 dígitos do meio do CPF, que ligação não entra no score, e as limitações: suplentes de vereador fora; TSE 2024 não divulga CPF de candidatos (por isso o rótulo "nome igual"); emendas marcadas só como "Maranhão (UF)" não são atribuídas a São Luís; senadores ligados ao TSE pelo nome; doações só da eleição do mandato atual.

- [ ] **Step 1: Write the failing tests**: `test_fornecedor_mostra_ligacao_com_politico` (contém nome de urna e o aviso); `test_fornecedor_sem_ligacao_nao_mostra_bloco`; `test_metodologia_explica_ligacoes` (contém "6 dígitos do meio" e "não entra no score").
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: ligações com políticos na página do fornecedor e na metodologia`

---

### Task 7: Coletor da Câmara (deputados, cota e projetos)

**Files:**
- Create: `app/services/coletores/camara.py`, `tests/fixtures/camara_deputados.json`, `camara_deputado.json`, `camara_despesas.json`, `camara_proposicoes.json`
- Modify: `app/cli.py`
- Test: `tests/test_camara.py`

**Interfaces:**
- Consumes: modelos, `texto.*`, `http.criar_sessao/get_json`.
- Produces: `coletar_camara(de: date, ate: date, get: Callable | None = None, pausa: float = 0.2) -> int` (retorna nº de deputados). Upsert `Politico` por `id_camara` (`cargo="Deputado Federal"`, `uf="MA"`, `nome=nomeCivil`, `nome_urna=ultimoStatus.nome`, `cpf`, `partido`, `foto_url`, `em_exercicio=True`, `ano_eleicao=2022`, `atualizar_busca()`); quem tinha `id_camara` e saiu da lista → `em_exercicio=False`. Despesas de cada ano entre `de.year` e `ate.year` (paginar até página vazia) → upsert `DespesaParlamentar`. Proposições `PL,PLP,PEC` desde `de` → upsert `Proposicao(casa="Câmara", url=f"https://www.camara.leg.br/propostas-legislativas/{id}")`.
- CLI: fonte `camara` antes de `tse`.

- [ ] **Step 1: Write the failing tests**: `test_coletar_camara_cria_deputados_com_cpf`; `test_despesas_e_proposicoes_gravadas` (valor Decimal, documento só dígitos, data date); `test_idempotente`; `test_quem_saiu_fica_fora_de_exercicio`. `get` falso despacha pela URL para os fixtures.
- [ ] **Step 2: Run** `pytest tests/test_camara.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** e registrar.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: coletor da Câmara (deputados do MA, cota e projetos)`

---

### Task 8: Coletor do Senado (senadores, projetos e CEAPS)

**Files:**
- Create: `app/services/coletores/senado.py`, `tests/fixtures/senado_lista.json`, `senado_processos.json`, `senado_ceaps.csv` (latin-1, com a linha `ULTIMA ATUALIZACAO` antes do cabeçalho)
- Modify: `app/cli.py`
- Test: `tests/test_senado.py`

**Interfaces:**
- Produces: `coletar_senado(de: date, ate: date, get: Callable | None = None, baixar_texto: Callable[[str], str] | None = None, pausa: float = 0.2) -> int`. Upsert `Politico` por `id_senado` (`cargo="Senador"`, `nome=NomeCompletoParlamentar`, `nome_urna=NomeParlamentar`, `ano_eleicao=None` até o TSE vincular). Projetos `PL`, `PLP`, `PEC` com `dataApresentacao >= de` → `Proposicao(casa="Senado", id_externo=codigoMateria, sigla/numero/ano` extraídos de `identificacao` `"PL 896/2023"`, `url=f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigoMateria}"`). CEAPS de cada ano entre `de.year` e `ate.year`: linhas com `normalizar(SENADOR) == normalizar(nome_urna)` → `DespesaParlamentar` (`cod_documento=COD_DOCUMENTO`).
- CLI: ordem final de `FONTES`: `pncp, cnpj, socios, sancoes, convenios, diario, camara, senado, tse, emendas`.

- [ ] **Step 1: Write the failing tests**: `test_coletar_senado_so_ma`; `test_identificacao_vira_sigla_numero_ano`; `test_ceaps_pula_linha_de_atualizacao_e_filtra_senador`; `test_idempotente`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** e registrar.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: coletor do Senado (senadores do MA, projetos e CEAPS)`

---

### Task 9: Emendas destinadas a São Luís

**Files:**
- Create: `tests/fixtures/emendas.json` (uma com `"SÃO LUÍS - MA"`, uma com `"MARANHÃO (UF)"`, uma de outro autor)
- Modify: `app/services/coletores/transparencia.py`, `app/cli.py`
- Test: `tests/test_transparencia.py`

**Interfaces:**
- Consumes: `_get_padrao`, `_paginas` (já existem), `Politico` federais.
- Produces: `coletar_emendas(de: date, ate: date, get: Callable | None = None, pausa: float = PAUSA_PADRAO) -> int` — para cada federal em exercício e cada ano entre `de.year` e `ate.year`, `GET {BASE}/emendas?ano=&nomeAutor=normalizar(nome_urna)`; grava só itens com `normalizar(nomeAutor) == normalizar(nome_urna)` e localidade começando com `SAO LUIS`; upsert por `codigo`. Sem chave → retorna 0 (mesmo comportamento das outras fontes).

- [ ] **Step 1: Write the failing tests**: `test_emendas_so_sao_luis_e_do_autor` (1 gravada de 3, valores Decimal); `test_emendas_idempotente`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** e registrar a fonte `emendas`.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: emendas parlamentares destinadas a São Luís`

---

### Task 10: Rodar de verdade e documentar

**Files:**
- Modify: `README.md` (CRLF — preservar), `sql/schema.sql` (regenerado)

- [ ] **Step 1:** `flask init-db` (cria só as tabelas novas; regrava `sql/schema.sql`).
- [ ] **Step 2:** Rodar, nesta ordem: `flask coletar --fonte socios`, `--fonte camara --de 2023-02-01`, `--fonte senado --de 2023-02-01`, `--fonte tse`, `--fonte emendas --de 2023-01-01`. Expected: 18 deputados, 3 senadores, prefeito + 31 vereadores; contagens de doações > 0; anotar as contagens.
- [ ] **Step 3:** Conferir no navegador: busca de um vereador e de um deputado; ao menos uma ficha com doadores; se houver ligação, seguir até o fornecedor e o contrato.
- [ ] **Step 4:** README: nova seção "Políticos" com as fontes, a ordem dos comandos acima e as limitações (mesmas da Metodologia).
- [ ] **Step 5: Commit** `docs: políticos no README e schema atualizado`
