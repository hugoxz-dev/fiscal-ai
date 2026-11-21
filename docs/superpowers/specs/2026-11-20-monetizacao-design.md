# Fiscal AI — Monetização: plano Pro e plano Institucional (design)

Data: 2026-11-20. Complementa `2026-11-17-fiscal-ai-design.md` e `2026-11-20-politicos-design.md`.

## Intenção e porquê

O objetivo é **mostrar à banca do TCC que o projeto tem um modelo de negócio viável**. Ninguém vai pagar de verdade agora. Por isso a cobrança é **simulada** (modo demonstração), mas as funções pagas **funcionam de verdade**. A banca deve ver um produto em que alguém pagaria, não só um slide.

O sucesso, na banca, é: abrir **Planos**, criar conta, "assinar" o Pro no checkout de demonstração, seguir um fornecedor, ver o aviso de novidade, baixar um CSV, imprimir o relatório de uma ficha, chamar a API com a chave e mostrar o formulário do plano Institucional.

## Modelo de negócio (o que a página Planos comunica)

| Plano | Para quem | Preço (demonstração) | O que tem |
|---|---|---|---|
| **Cidadão** | qualquer pessoa | grátis | todo o painel público de hoje, sem login |
| **Pro** | jornalista, assessor, pesquisador, ONG pequena | R$ 19,90/mês ou R$ 199/ano | monitoramento, exportação CSV, relatório para impressão, API (1.000 chamadas/dia) |
| **Institucional** | câmara municipal, redação, controle interno, outra prefeitura | sob consulta (a partir de R$ 490/mês por município) | instalação do Fiscal AI para outro município (o `IBGE_MUNICIPIO` é configurável), suporte e API sem limite; contratação via formulário "solicitar demonstração" |

## Objetivos

1. **Contas**: cadastro (nome, e-mail, senha), entrar e sair.
2. **Página Planos** (`/planos`) com os três planos.
3. **Checkout de demonstração**: escolher mensal ou anual, preencher um formulário de cartão de teste e virar Pro. Um aviso bem visível diz "Modo demonstração — nenhuma cobrança é feita". A conta mostra o plano, a validade e o botão "cancelar assinatura".
4. **Monitoramento (Pro)**: botão "Seguir" nas páginas de fornecedor e de político. A página **Meu painel** (`/conta/monitoramento`) lista o que a pessoa segue e as **novidades desde a última visita**: contratos novos do fornecedor, alertas novos do fornecedor e, para um político, contratos novos dos fornecedores ligados a ele. A navegação mostra um contador de novidades.
5. **Exportação CSV (Pro)**: botão "Baixar CSV" na lista de contratos, que respeita os filtros atuais, e nos alertas de um fornecedor.
6. **Relatório para impressão (Pro)**: versão limpa da ficha de fornecedor, de político e de contrato, com cabeçalho, data de geração, fontes e o aviso legal, pronta para "Imprimir / salvar PDF" do navegador.
7. **API (Pro)**: a página da conta gera e revoga uma chave. Endpoints JSON somente leitura, chamados com o cabeçalho `X-API-Key`:
   - `GET /api/v1/contratos` (filtros e paginação iguais aos da lista)
   - `GET /api/v1/contratos/<id>` (com os alertas)
   - `GET /api/v1/fornecedores/<id>` (com os alertas e as ligações com políticos)
   - `GET /api/v1/alertas`
   Limite de 1.000 chamadas por dia por chave (resposta 429 depois disso). Uma página `/api` documenta os endpoints com exemplos de `curl`.
8. **Plano Institucional**: formulário "Solicitar demonstração" (nome, órgão, município, e-mail, mensagem), gravado no banco, e o comando `flask leads` para listar os pedidos.
9. **Métricas do negócio para a banca**: comando `flask negocio resumo` com contas, assinantes Pro ativos, receita mensal simulada (MRR), itens seguidos, chamadas de API e pedidos institucionais.

## Não-objetivos

- Pagamento real (Pix, Stripe, Mercado Pago). O checkout só simula.
- E-mail de verdade (confirmação de cadastro, recuperar senha, alerta por e-mail). O aviso de novidade fica dentro do site. A página Planos diz "alerta por e-mail" como próximo passo do produto.
- Painel administrativo web. O administrador usa comandos `flask`.
- Hospedagem e deploy.

## Anti-objetivos (fracasso mesmo funcionando)

- **Fechar o dado público.** Tudo o que o painel mostra hoje continua grátis e sem login. O Pro vende conveniência (seguir, exportar, imprimir, integrar), nunca o acesso à informação.
- **Anúncio ou patrocínio.** Nada de propaganda, principalmente ao lado de político ou fornecedor, porque isso derruba a neutralidade.
- **Parecer cobrança de verdade.** O checkout não pode enganar ninguém. O aviso de demonstração aparece no checkout e na conta, e o sistema não guarda número de cartão (nem os 4 últimos dígitos).
- Senha em texto puro ou chave de API guardada em texto puro.

## Restrições

- Mesma pilha: Flask MVC, SQLAlchemy, MySQL do XAMPP e testes em SQLite em memória (`tests/conftest.py`).
- Nenhuma dependência nova. A senha usa `werkzeug.security` (já vem com o Flask), a sessão usa a sessão assinada do Flask, e a proteção CSRF é um token próprio na sessão, conferido em todo POST.
- `SECRET_KEY` entra no `Config`, vem do `.env` e tem um valor de desenvolvimento como padrão. Ela vai para a tabela de variáveis do README e para o `.env.example`.
- `base.html`, `inicio.html` e `fiscal.css` têm alterações do usuário ainda não commitadas. Os itens novos da navegação (Planos, Entrar / Minha conta e o contador de novidades) mexem no `base.html`. O commit deve incluir **só as linhas novas** (`git add -p`) ou perguntar ao usuário antes.
- Mudança de esquema: tabelas novas via `flask init-db` mais um arquivo `sql/migracao_2026-11-20-monetizacao.sql` para bancos já existentes, como foi feito antes.

## Abordagens consideradas

| | Abordagem | Trade-off | Decisão |
|---|---|---|---|
| A | Freemium: plano Pro com funções novas que funcionam | Mostra o diferencial pago funcionando e ainda melhora o produto; precisa de usuários, login e controle de acesso | **Escolhida** |
| B | Licença para outros municípios e instituições (B2G/B2B) | Modelo de receita mais realista para esse tipo de ferramenta, pouco código, mas sozinha é só uma página e um argumento | **Escolhida junto com A** (plano Institucional) |
| C | Só o documento do modelo de negócio, sem código | Barato, mas a banca não vê nada no sistema | Descartada |
| — | Anúncio ou cobrar pelo dado público | Destrói a credibilidade, que é o ativo principal | Descartada |

Na escolha de A + B, o usuário pediu **não cortar escopo por prazo**.

## Modelo de dados (proposta)

- `usuario`: id, nome, email (único, minúsculo), senha_hash, criado_em, ultima_visita_monitoramento.
- `contrato` (já existe): nova coluna `coletado_em`.
- `assinatura`: id, usuario_id, plano (`pro`/`institucional`), periodo (`mensal`/`anual`), valor (Decimal), status (`ativa`/`cancelada`), inicio, fim. O Pro está ativo quando `status == ativa` e `fim >= hoje`. O cancelamento mantém o Pro até `fim`.
- `seguido`: id, usuario_id, tipo (`fornecedor`/`politico`), alvo_id, criado_em. A combinação (usuario, tipo, alvo) é única.
- `chave_api`: id, usuario_id, prefixo (primeiros 8 caracteres, mostrados na conta), chave_hash (sha256), criada_em, revogada_em. Só uma chave ativa por usuário. A chave completa aparece **uma única vez**, logo depois de gerada.
- `uso_api`: chave_id, dia, chamadas. A combinação (chave, dia) é única.
- `pedido_institucional`: id, nome, orgao, municipio, email, mensagem, criado_em.

## Regras de acesso

- Sem login, o visitante vê o mesmo painel de hoje, mais Planos e a documentação da API.
- Logado sem Pro, os botões das funções Pro aparecem com um cadeado e levam a `/planos`. Eles não somem, porque a banca precisa ver o que é pago.
- Logado com Pro, tudo funciona.
- A API sem chave, ou com chave inválida ou revogada, responde 401 em JSON. Com chave válida de alguém cujo Pro venceu, responde 403.
- Rotas Pro sem login levam para "entrar" e, depois do login, voltam para a página de origem. O `next` só aceita caminho interno.

## "Novidades desde a última visita"

A data de referência é `ultima_visita_monitoramento`. Quando a conta nunca abriu o painel, vale a data em que a pessoa passou a seguir o item. Abrir **Meu painel** atualiza esse campo.

- **Contrato novo:** o `Contrato` ganha a coluna `coletado_em`, preenchida quando a coleta grava o contrato pela primeira vez e nunca alterada depois. A migração preenche os contratos já existentes com o momento da migração. Contrato novo é aquele com `coletado_em` depois da data de referência.
- **Alerta novo:** hoje `analisar_todos` apaga e recria todos os alertas com `criado_em = agora`, então qualquer análise faria tudo parecer novo. A correção (nossa decisão): ao recriar, se o contrato já tinha um alerta com a mesma `regra_codigo`, o novo alerta **herda o `criado_em` antigo**. Só alerta de regra que não existia antes no contrato recebe a hora atual. Pontos e evidência continuam sendo recalculados. Alerta novo é aquele com `criado_em` depois da data de referência.
- **Político seguido:** conta como novidade um contrato novo (pela regra acima) de um fornecedor com **ligação confirmada** com o político, calculada na hora pelo serviço `ligacoes`. Ligação só por nome (sem CPF para confirmar) não conta, para não avisar por causa de homônimo. Fornecedor que só passou a ter ligação depois não gera aviso retroativo de contratos antigos.

## Dados para a apresentação

O comando `flask negocio demo` cria algumas contas fictícias (algumas Pro mensais, algumas anuais, uma cancelada, uma institucional), itens seguidos, uso de API e dois pedidos institucionais. Assim o `flask negocio resumo` mostra números com cara de produto. Todas as contas fictícias usam o domínio `@demo.fiscal-ai.local` e o comando `flask negocio demo --limpar` as remove.

**O comando nunca cria contrato, alerta ou qualquer dado público inventado.** Para a banca ver novidades, ele cria a conta `banca@demo.fiscal-ai.local` (Pro, senha impressa no terminal). Essa conta segue os fornecedores reais com mais contratos e tem a data de referência recuada em 90 dias. As novidades que aparecem são contratos e alertas reais coletados nesse período.

## Privacidade nos dados exportados

A API e o CSV seguem a mesma regra do site: o **CPF de fornecedor pessoa física sai mascarado** (o mesmo formato do filtro de `_filtros.py`) e CPF de sócio, doador ou político nunca sai. CNPJ sai completo. As ligações com políticos na API têm os mesmos campos que a ficha mostra, nada além.

## Plano Institucional no sistema

`assinatura.plano` aceita `pro` ou `institucional`. A conta institucional é criada só pelo administrador (`flask negocio institucional --email X --meses N`), tem tudo do Pro e a API **sem limite diário** (sem 429). Na página Planos ela continua "sob consulta", contratada pelo formulário.

## Testes

Seguem o padrão atual (pytest e SQLite em memória): cadastro e login, senha com hash, CSRF recusando POST sem token, checkout ativando o Pro e cancelamento mantendo o Pro até o fim, bloqueio das rotas Pro, seguir e deixar de seguir, cálculo de novidades, CSV respeitando os filtros, API (401, 403, 429, formato do JSON), pedido institucional e os comandos `negocio`.

## Fica a critério de quem constrói

- O visual das páginas novas, seguindo o `fiscal.css` atual.
- Nomes exatos de rotas e templates, desde que coerentes com os blueprints atuais (sugestão: `contas`, `planos`, `monitoramento`, `exportacao`, `api`).
- O formato exato do JSON da API, reaproveitando os nomes de campos dos modelos.
- A seção da Metodologia ou do README que explica o modelo de negócio.
