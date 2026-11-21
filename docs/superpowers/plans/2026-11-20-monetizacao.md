# Monetização (Pro + Institucional) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Contas, plano Pro com checkout de demonstração, monitoramento, exportação CSV, relatórios para impressão, API com chave, plano Institucional e comandos de métricas, sem fechar nenhum dado público.

**Architecture:** Novos modelos em `app/models/conta.py`. Regras de negócio em serviços (`contas`, `monitoramento`, `exportacao`, `api_chaves`). Controle de acesso e CSRF em `app/controllers/_acesso.py`. Blueprints novos: `contas`, `planos`, `monitoramento`, `exportacao`, `api`. Comandos `flask negocio ...` e `flask leads` em `app/cli.py`.

**Tech Stack:** Flask 3.1, Flask-SQLAlchemy, MySQL (prod) / SQLite em memória (testes), pytest. **Nenhuma dependência nova.**

**Spec:** `docs/superpowers/specs/2026-11-20-monetizacao-design.md`

## Global Constraints

- Nenhuma dependência nova. Senha com `werkzeug.security.generate_password_hash`/`check_password_hash`. Chave de API com `secrets.token_urlsafe(32)` e hash `hashlib.sha256`.
- Todo o painel público atual continua acessível sem login. Os testes existentes (209) devem continuar passando.
- Preços: Pro mensal `Decimal("19.90")` por 30 dias; Pro anual `Decimal("199.00")` por 365 dias; Institucional "sob consulta (a partir de R$ 490/mês por município)".
- Limite da API: 1000 chamadas/dia por chave para `pro`; sem limite para `institucional`.
- Texto fixo do aviso de demonstração: "Modo demonstração — nenhuma cobrança é feita."
- Não guardar nenhum dado de cartão (nem os 4 últimos dígitos).
- CPF de fornecedor PF sai mascarado com `app.views._filtros.cnpj` em API e CSV; CPF de sócio, doador ou político nunca sai.
- Contas fictícias só com o domínio `@demo.fiscal-ai.local`. `negocio demo` nunca cria contrato, alerta ou dado público.
- `SECRET_KEY` vem do `.env` (padrão de desenvolvimento `"dev-fiscal-ai"`).
- Arquivos Python são LF. Ao gravar via script no Windows, use `newline=""`. O README é CRLF.
- `base.html`, `inicio.html` e `fiscal.css` têm alterações do usuário não commitadas. Os estilos novos vão em `app/static/conta.css` (arquivo novo). Antes de commitar `base.html`, siga a decisão do usuário registrada na execução: commitar as mudanças pendentes dele primeiro, num commit separado, ou deixar `base.html` fora dos commits.
- Branch: `monetizacao`, a partir de `main`.

## Review Focus

1. **Redirecionamento aberto em `next`:** `?next=https://evil.com` ou `//evil.com` deve cair em `/conta`. Teste na Task 3.
2. **E-mail com maiúsculas e espaços:** ` Ana@X.com ` cadastra como `ana@x.com`, e o login com `ANA@x.com` funciona. Cadastro duplicado mostra erro, sem 500. Teste na Task 3.
3. **Assinar de novo enquanto ainda é Pro:** não pode criar duas assinaturas ativas. A nova estende o `fim` da atual. Teste na Task 4.
4. **Chave de API num usuário cujo Pro venceu ou foi cancelado e já passou do fim:** responde 403 em JSON, nunca HTML nem 500. Teste na Task 7.
5. **Seguir duas vezes o mesmo alvo ou um id inexistente:** a segunda vez não faz nada, e o id inexistente dá 404. Teste na Task 5.

---

### Task 1: Datas estáveis para "novidade" (contrato.coletado_em e alertas que mantêm o criado_em)

**Files:**
- Modify: `app/models/contrato.py`, `app/services/analisador.py:45-50`
- Create: `sql/migracao_2026-11-20-monetizacao.sql`
- Test: `tests/test_analisador.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `Contrato.coletado_em: DateTime, nullable=False, default=datetime.now`. É gravado só na inserção, e `upsert_contrato` nunca altera.

- [ ] **Step 1: Testes que falham**

```python
def test_contrato_ganha_coletado_em(fazer_contrato):
    c = fazer_contrato()
    assert c.coletado_em is not None

def test_reanalise_preserva_criado_em_de_alerta_da_mesma_regra(app, fazer_contrato):
    # contrato que dispara uma regra determinística (use o mesmo arranjo de um teste existente de test_analisador.py)
    # 1ª análise -> guarda alerta.criado_em; força criado_em = datetime(2025,1,1); commit
    # 2ª análise -> o alerta da mesma regra_codigo tem criado_em == datetime(2025,1,1)
    ...
def test_reanalise_alerta_de_regra_nova_recebe_hora_atual(...):
    # alerta pré-existente de regra X; 2ª análise produz regra Y também -> Y.criado_em > datetime(2025,1,1)
```

- [ ] **Step 2:** `pytest tests/test_analisador.py tests/test_models.py -q` → FAIL
- [ ] **Step 3: Implementar.** Adicione a coluna. Em `analisar_todos`, antes de `contrato.alertas.clear()`, monte `antigos = {a.regra_codigo: a.criado_em for a in contrato.alertas}` e use `criado_em=antigos.get(res.codigo, agora)`. Migração SQL:

```sql
-- Monetização: data em que o contrato entrou no banco (base das "novidades").
ALTER TABLE contrato ADD COLUMN coletado_em DATETIME NULL;
UPDATE contrato SET coletado_em = NOW() WHERE coletado_em IS NULL;
ALTER TABLE contrato MODIFY coletado_em DATETIME NOT NULL;
```

- [ ] **Step 4:** `pytest -q` → todos passam
- [ ] **Step 5:** commit `feat: coletado_em no contrato e alertas reanalisados mantêm a data original`

### Task 2: Modelos de conta, configuração e fixtures

**Files:**
- Create: `app/models/conta.py`
- Modify: `app/models/__init__.py`, `app/config.py`, `.env.example`, `tests/conftest.py`, `sql/migracao_2026-11-20-monetizacao.sql` (acrescentar os `CREATE TABLE`, gerados com `CreateTable(...).compile(dialect=mysql.dialect())` como faz `gravar_schema_sql`)
- Test: `tests/test_models.py`

**Interfaces (Produces):**
- `Usuario(id, nome String(120), email String(190) unique, senha_hash String(255), criado_em, ultima_visita_monitoramento DateTime nullable)`. Relações: `assinaturas`, `seguidos`, `chaves`.
- `Assinatura(id, usuario_id FK, plano String(20) 'pro'|'institucional', periodo String(10) 'mensal'|'anual'|'manual', valor Dinheiro, status String(10) 'ativa'|'cancelada', inicio Date, fim Date)`
- `Seguido(id, usuario_id FK, tipo String(12) 'fornecedor'|'politico', alvo_id Integer, criado_em)` com UniqueConstraint(usuario_id, tipo, alvo_id)
- `ChaveApi(id, usuario_id FK, prefixo String(8), chave_hash String(64) unique, criada_em, revogada_em nullable)`
- `UsoApi(id, chave_id FK, dia Date, chamadas Integer default 0)` com UniqueConstraint(chave_id, dia)
- `PedidoInstitucional(id, nome, orgao, municipio, email String(190), mensagem Text, criado_em)`
- `Config.SECRET_KEY = os.getenv("SECRET_KEY", "dev-fiscal-ai")`, `Config.CSRF_ATIVO = True`
- Fixtures do conftest: `app` passa `CSRF_ATIVO: False`. `fazer_usuario(email="ana@x.com", senha="segredo123", plano=None|"pro"|"institucional", fim=None) -> Usuario`, que cria a assinatura ativa quando `plano` é informado (fim padrão = hoje + 30). `logar(client, usuario)` grava `session["usuario_id"]` via `client.session_transaction()`.

- [ ] **Step 1:** teste `test_modelos_de_conta_persistem` (cria um de cada, commit, relê) e `test_seguido_unico` (o segundo insert igual levanta `IntegrityError`)
- [ ] **Step 2:** rodar → FAIL
- [ ] **Step 3:** implementar modelos, config, `.env.example` (`SECRET_KEY=troque-isto`) e fixtures
- [ ] **Step 4:** `pytest -q` → passa
- [ ] **Step 5:** commit `feat: modelos de usuário, assinatura, seguidos, chave de API e pedido institucional`

### Task 3: Cadastro, login, sessão e CSRF

**Files:**
- Create: `app/services/contas.py`, `app/controllers/_acesso.py`, `app/controllers/contas.py`, `app/views/conta_entrar.html`, `app/views/conta_cadastro.html`, `app/views/conta.html`, `app/static/conta.css`
- Modify: `app/__init__.py` (blueprint, `before_request` do CSRF, context processor), `app/views/base.html` (links "Planos" e "Entrar"/"Minha conta", `<link>` para `conta.css`)
- Test: `tests/test_contas.py`

**Interfaces (Produces):**
- `contas.criar_usuario(nome: str, email: str, senha: str) -> Usuario`. Normaliza o e-mail com `strip().lower()` e exige senha com 8 caracteres ou mais e e-mail com `@`. Levanta `ValueError(mensagem_em_pt)` em caso de inválido ou duplicado.
- `contas.autenticar(email: str, senha: str) -> Usuario | None`
- `contas.assinatura_ativa(u: Usuario, hoje: date | None = None) -> Assinatura | None`. Vale `status in ('ativa','cancelada')` e `fim >= hoje`, porque o cancelamento mantém o acesso até o fim. Retorna a de maior `fim`.
- `contas.e_pro(u: Usuario | None) -> bool`
- `_acesso.usuario_atual() -> Usuario | None` (cache em `g`), `_acesso.login_obrigatorio(view)`, `_acesso.pro_obrigatorio(view)`. Sem login, redireciona para `contas.entrar?next=<path>`. Sem Pro, redireciona para `planos.pagina` com o flash "Recurso do plano Pro.".
- `_acesso.csrf_token() -> str` (guardado em `session["csrf"]`), exposto ao Jinja como `csrf_token()`. `_acesso.conferir_csrf()`, como `before_request`: com `CSRF_ATIVO`, todo POST fora de `/api/` exige o campo `csrf` igual ao da sessão, senão `abort(400)`.
- `_acesso.next_seguro(valor: str | None) -> str`: aceita só caminho que começa com `/` e não com `//`. Caso contrário, devolve `url_for("contas.minha_conta")`.
- Context processor global: `usuario_atual`, `e_pro_atual` (bool), `novidades_qtd` (0 por enquanto; a Task 5 liga).
- Rotas: `GET/POST /entrar`, `GET/POST /cadastro`, `POST /sair`, `GET /conta` (login obrigatório; mostra o plano, a validade e o aviso de demonstração se houver assinatura).

- [ ] **Step 1: Testes que falham**

```python
def test_cadastro_normaliza_email_e_guarda_hash(client, app):
    r = client.post("/cadastro", data={"nome": "Ana", "email": " Ana@X.com ", "senha": "segredo123"})
    assert r.status_code == 302
    u = Usuario.query.one(); assert u.email == "ana@x.com" and u.senha_hash != "segredo123"
def test_cadastro_duplicado_mostra_erro(client, fazer_usuario):  # 200, "já cadastrado" no HTML
def test_login_com_email_em_maiusculas(client, fazer_usuario)   # POST /entrar ANA@x.com -> 302 /conta
def test_login_senha_errada(client, fazer_usuario)               # 200 + "E-mail ou senha inválidos"
def test_next_externo_ignorado(client, fazer_usuario):
    for n in ("https://evil.com", "//evil.com"):
        r = client.post(f"/entrar?next={n}", data={...}); assert r.headers["Location"].endswith("/conta")
def test_conta_exige_login(client)                               # GET /conta -> 302 /entrar?next=/conta
def test_post_sem_csrf_recusado():                               # create_app({... "CSRF_ATIVO": True}) -> POST /entrar sem csrf = 400
def test_painel_publico_continua_sem_login(client)               # GET /, /contratos, /politicos -> 200
```

- [ ] **Step 2:** rodar → FAIL
- [ ] **Step 3:** implementar. Todos os formulários usam `<input type="hidden" name="csrf" value="{{ csrf_token() }}">`.
- [ ] **Step 4:** `pytest -q` → passa
- [ ] **Step 5:** commit `feat: contas de usuário com login e proteção CSRF`

### Task 4: Página Planos, checkout de demonstração, cancelamento e pedido institucional

**Files:**
- Create: `app/controllers/planos.py`, `app/views/planos.html`, `app/views/checkout.html`, `app/views/institucional_obrigado.html`
- Modify: `app/services/contas.py`, `app/views/conta.html`
- Test: `tests/test_planos.py`

**Interfaces (Produces):**
- `contas.PRECOS = {"mensal": Decimal("19.90"), "anual": Decimal("199.00")}`, `contas.DURACAO = {"mensal": 30, "anual": 365}`
- `contas.assinar(u: Usuario, periodo: str, hoje: date | None = None) -> Assinatura`. Período inválido levanta `ValueError`. Se já existe assinatura ativa ou cancelada ainda vigente, **estende** o `fim` dela pela duração, atualiza `periodo` e `valor` e volta o `status` para `ativa`. Não cria outra.
- `contas.cancelar(u: Usuario) -> None`: `status = 'cancelada'`, `fim` mantido.
- Rotas: `GET /planos` (três cartões com os textos da spec; o Institucional tem o formulário "Solicitar demonstração"), `GET/POST /planos/checkout?periodo=mensal|anual` (login obrigatório; o formulário de cartão de teste tem número, nome, validade e CVV, que são validados só por preenchimento e **descartados**; mostra o aviso de demonstração), `POST /conta/cancelar`, `POST /planos/institucional` (validação: nome, órgão, município e e-mail com `@` obrigatórios; grava o `PedidoInstitucional`; mostra a página de obrigado).

- [ ] **Step 1: Testes que falham**

```python
def test_planos_publico_mostra_tres_planos_e_precos(client)  # "Cidadão", "Pro", "Institucional", "19,90", "199", "sob consulta"
def test_checkout_exige_login(client)
def test_checkout_ativa_pro_sem_guardar_cartao(client, fazer_usuario, logar):
    # POST periodo=anual + numero=4111111111111111 -> e_pro True, fim = hoje+365, valor 199.00
    # nenhum campo de nenhuma tabela contém "4111" nem "1111"
def test_checkout_mostra_aviso_demo(client, ...)            # "Modo demonstração — nenhuma cobrança é feita."
def test_assinar_de_novo_estende(app, fazer_usuario):        # 2x mensal -> 1 assinatura, fim = hoje+60
def test_cancelar_mantem_ate_fim(app, fazer_usuario)        # e_pro continua True; com hoje=fim+1 -> False
def test_pedido_institucional_grava(client)                 # POST válido -> 1 PedidoInstitucional; inválido -> 0 e mensagem
```

- [ ] **Step 2–4:** FAIL → implementar → `pytest -q` passa
- [ ] **Step 5:** commit `feat: planos, checkout de demonstração e pedido institucional`

### Task 5: Monitoramento (seguir e novidades)

**Files:**
- Create: `app/services/monitoramento.py`, `app/controllers/monitoramento.py`, `app/views/monitoramento.html`, `app/views/_botao_seguir.html`
- Modify: `app/__init__.py` (o `novidades_qtd` real no context processor, calculado só para usuário Pro), `app/views/fornecedor.html`, `app/views/politico.html` (incluir `_botao_seguir.html`)
- Test: `tests/test_monitoramento.py`

**Interfaces (Produces):**
- `monitoramento.seguir(u, tipo: str, alvo_id: int) -> Seguido`. É idempotente. Alvo inexistente levanta `LookupError`, e tipo inválido levanta `ValueError`.
- `monitoramento.deixar(u, tipo, alvo_id) -> None`
- `monitoramento.segue(u, tipo, alvo_id) -> bool`
- `monitoramento.novidades(u) -> list[dict]`, um item por `Seguido`: `{"seguido": Seguido, "alvo": Fornecedor|Politico, "contratos": list[Contrato], "alertas": list[Alerta]}`. A referência é `max(u.ultima_visita_monitoramento, s.criado_em)` quando a visita existe, senão `s.criado_em`.
  - Fornecedor: contratos dele com `coletado_em > ref` e alertas dos contratos dele com `criado_em > ref`.
  - Político: contratos com `coletado_em > ref` dos fornecedores de `ligacoes_do_politico(p)` com `confirmada=True`. Alertas: lista vazia.
- `monitoramento.contar(u) -> int`: soma de contratos e alertas de todas as novidades.
- Rotas: `POST /seguir/<tipo>/<int:id>` e `POST /deixar/<tipo>/<int:id>` (Pro obrigatório; redirecionam para o `next_seguro` do referer/`next`). `GET /conta/monitoramento` (Pro obrigatório; renderiza `novidades(u)` e **depois** grava `u.ultima_visita_monitoramento = datetime.now()`).
- `_botao_seguir.html` recebe `tipo` e `alvo_id`. Sem Pro, mostra o botão com cadeado, que leva para `/planos`. Com Pro, mostra o formulário Seguir/Deixar de seguir.
- Na navegação, quando `novidades_qtd > 0`, um selo com o número aparece ao lado de "Minha conta".

- [ ] **Step 1: Testes que falham**

```python
def test_seguir_idempotente_e_404(client, fazer_usuario, logar, fazer_contrato)  # 2x -> 1 Seguido; id 9999 -> 404
def test_seguir_sem_pro_vai_para_planos(client, ...)                             # 302 /planos
def test_novidade_de_contrato_e_alerta(app, ...):
    # segue o fornecedor com criado_em = 2025-01-01; contrato A com coletado_em = 2024-12-01 e B com 2025-02-01
    # -> novidades: só B; alerta de B com criado_em 2025-02-01 conta
def test_abrir_painel_zera_contador(client, ...)                                 # contar > 0; GET /conta/monitoramento; contar == 0
def test_politico_so_conta_ligacao_confirmada(app, ...)                          # monte uma ligação confirmada e uma só por nome como em tests/test_ligacoes.py
def test_fornecedor_mostra_botao_com_cadeado_sem_login(client, fazer_contrato)   # "/planos" no HTML da ficha
```

- [ ] **Step 2–4:** FAIL → implementar → `pytest -q` passa
- [ ] **Step 5:** commit `feat: seguir fornecedores e políticos com novidades desde a última visita`

### Task 6: Exportação CSV e relatórios para impressão

**Files:**
- Create: `app/services/exportacao.py`, `app/controllers/exportacao.py`, `app/views/relatorio_base.html`, `app/views/relatorio_fornecedor.html`, `app/views/relatorio_politico.html`, `app/views/relatorio_contrato.html`
- Modify: `app/controllers/contratos.py` (extrair `filtrar_contratos(args) -> tuple[Query, dict]` de `lista()`, sem mudar o comportamento), `app/controllers/fornecedores.py` e `politicos.py` (extrair a montagem do contexto da ficha numa função reutilizável pelo relatório), `app/views/contratos.html`, `fornecedor.html`, `politico.html`, `contrato_detalhe.html` (botões "Baixar CSV" / "Relatório para impressão", com cadeado quando não for Pro)
- Test: `tests/test_exportacao.py`

**Interfaces (Produces):**
- `exportacao.documento_publico(f: Fornecedor) -> str`: `_filtros.cnpj(f.documento)`, então o CPF sai mascarado.
- `exportacao.contrato_dict(c: Contrato, com_alertas: bool = False) -> dict`, com as chaves `id, numero_controle_pncp, objeto, orgao, fornecedor{id,nome,documento,tipo}, valor_inicial, valor_global (str), data_assinatura (ISO), modalidade, score, nivel, link_pncp, url` e, se pedido, `alertas`.
- `exportacao.alerta_dict(a: Alerta) -> dict` (`regra_codigo, pontos, evidencia, criado_em`)
- `exportacao.fornecedor_dict(f: Fornecedor) -> dict`, com `alertas` e `ligacoes` (só os campos que a ficha mostra: `tipo, confirmada, politico{id,nome,cargo,partido}, pessoa, valor, descricao`)
- `exportacao.contratos_csv(contratos) -> str`: separador `;`, BOM UTF-8 para o Excel abrir com acentos, valores em formato brasileiro (`1234,50`) e cabeçalho em português.
- Rotas (Pro obrigatório): `GET /contratos.csv` (mesmos filtros de `/contratos`, sem paginação), `GET /fornecedores/<id>/alertas.csv`, `GET /relatorio/fornecedor/<id>`, `GET /relatorio/politico/<id>`, `GET /relatorio/contrato/<id>`.
- O relatório traz cabeçalho "Fiscal AI — Relatório", a data e hora de geração, o `AVISO`, a lista de fontes e o botão "Imprimir / salvar PDF" (`onclick="window.print()"`, escondido com `@media print`).

- [ ] **Step 1: Testes que falham**

```python
def test_csv_respeita_filtro(client, pro_logado, fazer_contrato)   # nivel=Alto -> só as linhas Alto; Content-Type text/csv
def test_csv_mascara_cpf(client, pro_logado, fazer_contrato)       # fornecedor PF 12345678901 -> "***.456.789-**", nunca "12345678901"
def test_csv_exige_pro(client)                                     # 302
def test_relatorio_fornecedor_tem_aviso_e_data(client, pro_logado, ...)
def test_lista_contratos_inalterada(client, fazer_contrato)        # os testes existentes de test_contratos_views.py continuam passando
```

(Use `pro_logado` como fixture local do arquivo: `fazer_usuario(plano="pro")` + `logar`.)

- [ ] **Step 2–4:** FAIL → implementar → `pytest -q` passa
- [ ] **Step 5:** commit `feat: exportação CSV e relatórios para impressão do plano Pro`

### Task 7: API v1 com chave e limite diário

**Files:**
- Create: `app/services/api_chaves.py`, `app/controllers/api.py`, `app/views/api_docs.html`
- Modify: `app/views/conta.html` (seção "Chave de API": gerar e revogar; a chave completa aparece uma vez via flash), `app/controllers/contas.py` (`POST /conta/chave`, `POST /conta/chave/revogar`, Pro obrigatório)
- Test: `tests/test_api.py`

**Interfaces (Produces):**
- `api_chaves.LIMITE_DIARIO = 1000`
- `api_chaves.gerar(u: Usuario) -> str`: revoga a ativa anterior e devolve `"fai_" + secrets.token_urlsafe(32)`. Guarda `prefixo = chave[:8]` e `chave_hash = sha256(chave)`.
- `api_chaves.revogar(u) -> None`
- `api_chaves.validar(texto: str | None) -> ChaveApi | None`: só chave não revogada.
- `api_chaves.registrar_uso(chave: ChaveApi, hoje: date | None = None) -> int`: incrementa e devolve as chamadas do dia.
- Em `/api/v1/*`, um `before_request` do blueprint faz: sem chave ou chave inválida → 401 `{"erro": "chave de API ausente ou inválida"}`. Dono sem Pro/Institucional vigente → 403 `{"erro": "assinatura Pro inativa"}`. Plano `pro` passando de `LIMITE_DIARIO` → 429 `{"erro": "limite diário de 1000 chamadas atingido"}`. Toda resposta leva os cabeçalhos `X-Limite-Diario` e `X-Chamadas-Hoje`.
- Endpoints: `GET /api/v1/contratos` (filtros de `filtrar_contratos`, `pagina`, `por_pagina` ≤ 100; resposta `{"pagina", "total", "itens": [contrato_dict]}`), `GET /api/v1/contratos/<id>` (`com_alertas=True`), `GET /api/v1/fornecedores/<id>` (`fornecedor_dict`), `GET /api/v1/alertas` (`?regra=`, paginado). 404 em JSON.
- `GET /api` (público): documentação com os exemplos `curl -H "X-API-Key: ..." http://127.0.0.1:5000/api/v1/contratos?nivel=Alto`.

- [ ] **Step 1: Testes que falham**

```python
def test_api_sem_chave_401(client)
def test_api_chave_revogada_401(...)
def test_api_pro_vencido_403(...)                  # assinatura com fim = ontem -> 403 JSON
def test_api_limite_429(app, ...)                  # UsoApi do dia com chamadas=1000 -> 429; o institucional com 5000 passa
def test_api_contratos_formato_e_cpf_mascarado(...)
def test_chave_completa_nao_fica_no_banco(...)     # nenhum ChaveApi.chave_hash/prefixo == chave completa
def test_api_docs_publica(client)                  # GET /api 200
```

- [ ] **Step 2–4:** FAIL → implementar → `pytest -q` passa
- [ ] **Step 5:** commit `feat: API v1 com chave, limite diário e documentação`

### Task 8: Comandos `flask negocio` e `flask leads`

**Files:**
- Create: `app/services/negocio.py`
- Modify: `app/cli.py`
- Test: `tests/test_negocio.py`

**Interfaces (Produces):**
- `negocio.resumo(hoje: date | None = None) -> dict` com as chaves `contas, pro_ativos, institucionais_ativos, mrr (Decimal: soma de mensal + anual/12 dos vigentes não cancelados), cancelamentos, seguidos, chamadas_api_30d, pedidos_institucionais`.
- `negocio.criar_demo() -> str`: cria 8 contas `demo1..demo8@demo.fiscal-ai.local` (4 mensais, 2 anuais, 1 cancelada, 1 institucional), seguidos em fornecedores e políticos **reais existentes**, `UsoApi` dos últimos 14 dias e 2 pedidos institucionais com e-mail `@demo.fiscal-ai.local`. Também cria `banca@demo.fiscal-ai.local` (Pro), que segue os 3 fornecedores com mais contratos, com `criado_em` dos seguidos = agora − 90 dias e `ultima_visita_monitoramento = None`. Devolve a senha da conta da banca (`secrets.token_urlsafe(9)`). É idempotente: chama `limpar_demo()` primeiro.
- `negocio.limpar_demo() -> int`: apaga usuários e pedidos com e-mail terminando em `@demo.fiscal-ai.local`, com seus dependentes.
- `negocio.criar_institucional(email: str, meses: int) -> Assinatura`: o usuário precisa existir; cria a assinatura `plano='institucional', periodo='manual', valor=Decimal('0')`, com fim = hoje + 30·meses.
- CLI: `flask negocio resumo`, `flask negocio demo [--limpar]`, `flask negocio institucional --email X --meses N`, `flask leads` (lista os pedidos, do mais novo para o mais antigo).

- [ ] **Step 1: Testes que falham**

```python
def test_demo_nao_cria_dado_publico(app, fazer_contrato):  # conta Contrato/Alerta/Fornecedor/Politico antes == depois
def test_demo_idempotente_e_limpar(app, fazer_contrato)   # 2x demo -> 9 usuários demo; limpar -> 0; usuário real intacto
def test_resumo_mrr(app, fazer_usuario)                   # 1 mensal 19.90 + 1 anual 199 -> mrr == Decimal("36.48") (arredondado a 2 casas)
def test_institucional_sem_limite(app, fazer_usuario)
def test_cli_leads(app)                                    # app.test_cli_runner().invoke(args=["leads"]) lista o pedido
```

- [ ] **Step 2–4:** FAIL → implementar → `pytest -q` passa
- [ ] **Step 5:** commit `feat: comandos de métricas, dados de demonstração e plano institucional`

### Task 9: Documentação e esquema

**Files:**
- Modify: `README.md` (CRLF: seções "Planos e modelo de negócio", "Contas e API", `SECRET_KEY` na tabela de variáveis, a migração nova, os comandos `negocio`/`leads`), `app/views/metodologia.html` (parágrafo curto: "O que é grátis e o que é Pro", reafirmando que o dado público nunca é fechado), `sql/schema.sql` (regerar com `gravar_schema_sql`)
- Test: nenhum novo; `pytest -q` precisa continuar passando

- [ ] **Step 1:** editar os docs e regerar o `sql/schema.sql` com `python -c "from app import create_app; from app.cli import gravar_schema_sql; app=create_app({'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'}); app.app_context().push(); gravar_schema_sql('sql/schema.sql')"`
- [ ] **Step 2:** `pytest -q` → passa
- [ ] **Step 3:** subir o app (`flask run`), rodar `flask negocio demo`, entrar como `banca@demo.fiscal-ai.local` e conferir no navegador: Planos → Meu painel com novidades → CSV → relatório → gerar a chave → `curl` na API
- [ ] **Step 4:** commit `docs: modelo de negócio, contas e API no README e na metodologia`
