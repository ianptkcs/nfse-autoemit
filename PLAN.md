# Implementation plan — nfse-autoemit

Working notes for implementation. Not part of the public-facing docs — feel
free to delete once the code lands, or keep as an internal design record.

## Part 1 — Architecture plan (from planner, Opus)

### 0. Nome, org e localização

- Diretório: `/home/ianptkcs/codigo/pessoal/nfse-autoemit` — já criado.
- Repo público: `github.com/ianptkcs/nfse-autoemit` — já criado e com o
  scaffold inicial commitado/pushado.

### 1. O que o `tscaf` já cobre vs. o que falta desenhar

Já aplicado: `.github/workflows/{ci,release}.yml`, `LICENSE` (AGPL-3.0),
`CHANGELOG.md`, `CONTRIBUTING.md`/`CONTRIBUTING.pt-BR.md`, templates de
issue/PR, badges no README, `pyproject.toml` (com os ajustes abaixo já
aplicados), `.gitignore`, `typos.toml`, `uv.lock`.

`pyproject.toml` já tem:
- `dependencies = ["playwright", "python-dotenv"]`
- `[tool.pytest.ini_options]` com `pythonpath = ["bin"]`,
  `addopts = "-q -m 'not integration'"`,
  `markers = ["integration: exercises the real portal (requires NFSE_LIVE=1)"]`

Falta escrever (não é do tscaf): todo o código em `bin/`, os testes em
`tests/`, `.env.example`, o corpo final dos READMEs.

Depois de codar: `uv run ruff format .` antes de commitar (CI roda
`--check`), e reexecutar `uv lock` se mudar deps.

Layout de código: **`bin/` plano**, módulos snake_case, sem `src/`. API
síncrona do Playwright (`sync_playwright`), não async — é script one-shot
mensal, sem concorrência.

### 2. Estrutura de arquivos

```
nfse-autoemit/
  bin/
    nfse_config.py      # NotaConfig: env -> dataclass, normalização, validação, redaction
    nfse_selectors.py   # TODOS os locators, agrupados por etapa
    nfse_browser.py     # launch do contexto persistente, timeouts, artifacts, sessão
    nfse_wizard.py      # fill_pessoas / fill_servico / fill_tributacao / read_review
    nfse_submit.py      # ÚNICO lugar que clica "Emitir NFS-e"
    nfse_emit.py        # CLI (argparse): login | config | preview | emit
  tests/
    test_config.py
    test_review.py
    test_safety.py
    test_no_secrets.py
    integration/test_live_wizard.py   # @pytest.mark.integration
  .env.example
```

Invocação: `uv run bin/nfse_emit.py preview` (sem console script, `[tool.uv]
package = false`).

### 3. Autenticação e sessão

**Decisão: contexto persistente (`launch_persistent_context`), não
`storage_state`.** `storage_state` só salva cookies + localStorage; o
gov.br/Angular costuma guardar token em `sessionStorage`, que se perde. O
perfil persistente mantém o browser "parecendo" o mesmo entre execuções,
reduzindo chance de pedir 2FA de novo.

- Perfil em `$XDG_STATE_HOME/nfse-autoemit/chromium-profile` (default
  `~/.local/state/nfse-autoemit/chromium-profile`), `chmod 700`, **nunca**
  dentro do repo.
- `headless=False` por padrão (`NFSE_HEADLESS=1` pra opt-in) — gov.br
  costuma bloquear headless, e o fluxo é mensal/supervisionado.
- `nfse_emit.py login`: abre `{BASE_URL}/EmissorNacional/Login`, espera
  `page.wait_for_url(lambda u: "/Login" not in u, timeout=300_000)`.
- `is_session_expired(page)`: `"/EmissorNacional/Login" in page.url` — chamar
  depois de CADA navegação e reload, não só no início. Confirmado no
  mapeamento manual: um reload simples já derrubou a sessão.
- Se detectar expiração em `preview`/`emit` E stdin for TTY E headed: fazer
  login interativo *in-place*, no mesmo processo, e continuar — evita forçar
  dois comandos separados numa janela onde o TTL é curto.

### 4. Configuração / variáveis de ambiente

`nfse_config.py`: dataclass frozen `NotaConfig` + `load_config(env: Mapping)
-> NotaConfig` **puro** (recebe mapping, não lê `os.environ` direto — fica
testável sem browser).

`.env.example`:

```dotenv
# --- obrigatorios ---
NFSE_TOMADOR_CNPJ=00000000000191
NFSE_VALOR=0,00
NFSE_DESCRICAO_SERVICO=Descricao do servico prestado
NFSE_CODIGO_TRIBUTACAO=000000
NFSE_MUNICIPIO_PRESTACAO=Nome da Cidade
NFSE_MUNICIPIO_UF=XX

# --- opcionais / guardas ---
NFSE_COMPETENCIA=
NFSE_EMITENTE_CNPJ=
NFSE_TOMADOR_NOME_ESPERADO=

# --- ambiente ---
# producao restrita (SEM validade fiscal) - default seguro
NFSE_BASE_URL=https://www.producaorestrita.nfse.gov.br
# producao real: https://www.nfse.gov.br
NFSE_HEADLESS=0
NFSE_TIMEOUT_MS=20000
NFSE_SLOW_MO_MS=0
NFSE_PROFILE_DIR=
NFSE_ARTIFACT_DIR=
```

**Ambiente de produção restrita**: `https://www.producaorestrita.nfse.gov.br`
— mesmas rotas, sem validade fiscal. Cadastro separado
(`/Acesso/PrimeiroAcesso`), e **o histórico de tomadores fica vazio lá**
(daí o fallback do item 6 abaixo). Usar como default do `.env.example`
permite testar o fluxo inteiro, incluindo o clique final, sem risco.

Normalizações (tudo unit-testado): CNPJ (mascarado ou dígitos, valida DV);
valor (`2000`/`2000.00`/`2000,00` → `"2.000,00"`); competência (vazia →
hoje, formato `dd/mm/aaaa`); rótulo de município `f"{municipio}/{uf}"`;
faltando obrigatório → erro lista TODOS de uma vez; `redact()` mascara
CNPJ/CPF em qualquer print/log.

### 5. Wizard — desenho

**Seletores centralizados** em `nfse_selectors.py`. Preferir `get_by_label` /
`get_by_role` com rótulo visível (ver Parte 2 abaixo pros rótulos exatos) a
CSS/XPath.

**Armadilha:** rótulos se repetem entre seções (emitente e tomador têm
"CPF/CNPJ", "Nome/Razão Social"). Nunca `get_by_label` global — ancorar num
container por heading (`page.locator("section", has=page.get_by_role(...))`
ou equivalente; validar com teste de integração que o container casa 1
elemento).

**Navegação nunca por URL construída** — o `idr` na query string é opaco e
muda a cada entrada no wizard. Só navegar clicando "Avançar" e validar com
`wait_for_url(re.compile(r"/DPS/Servico"))` etc.

**Helpers em `nfse_browser.py`:**
- `select_searchable(scope, field, query, option_label)` — clica, digita
  (`press_sequentially`, delay 50ms), espera a opção, clica, lê de volta pra
  confirmar. Usado no Município e no Código de Tributação.
- `fill_masked(locator, expected)` — campos com máscara (data, valor) às
  vezes ignoram `fill()` puro: `fill()` → ler `input_value()` → se divergir,
  `clear()` + `press_sequentially()` dígito a dígito → reler → se ainda
  divergir, levantar exceção. Sem isso dá pra emitir nota com valor errado
  silenciosamente.
- `ensure_radio(scope, group_label, option)` — marca E assere. Usar até nos
  radios que já vêm certos por default (barato, pega drift do portal).
- `retry_step(page, fn, attempts=3)` — retry por ETAPA INTEIRA, não por
  campo: ao falhar, detecta modal de erro, fecha, `page.reload()`, checa
  sessão, reexecuta `fn` do zero. O erro "Não foi possível recuperar a lista
  de municípios" trava o campo — só reload resolve.
  - Consequência: cada `fill_*` precisa ser idempotente sob reload. Etapas
    Serviço/Valores preservam estado via `idr` (reexecutar é seguro, helpers
    leem de volta e não duplicam); Pessoas não tem `idr`, reload zera, e por
    isso a função já recomeça do topo naturalmente.
- `is_error_modal(page)` — procura dialog com "Não foi possível", retorna
  texto pra log.

**Função pura e testável sem browser:**
`check_review(summary: ReviewSummary, cfg: NotaConfig) -> list[str]` — lista
divergências entre o que foi preenchido e o que apareceu na revisão final.
Qualquer divergência = abort, nunca "aviso".

### 6. Segurança do clique final

1. `nfse_submit.py` é o **único** módulo que referencia o botão "Emitir
   NFS-e" — pequeno, fácil de auditar via grep.
2. `def submit(page, summary, *, confirmed: bool) -> str` — levanta
   `RuntimeError` se `confirmed is not True`. Sem default.
3. `preview` é o subcomando padrão: roda até a revisão, imprime o
   `ReviewSummary` (CNPJ redigido), salva screenshot full-page, encerra.
4. `emit` exige DUAS portas: flag `--confirm` E digitar literalmente
   `EMITIR` no stdin.
5. Se stdin não for TTY, `emit` aborta mesmo com `--confirm` — sem escape
   por env var, sem `--yes`. Sem caso de uso legítimo de emitir de dentro de
   um cron (mata de propósito a ideia de agendar isso).
6. `check_review` roda ANTES do prompt — divergência aborta sem nem
   oferecer confirmação.
7. Pós-emissão: espera indicador de sucesso, captura número da NFS-e,
   screenshot + XML/PDF se disponível, tudo em `NFSE_ARTIFACT_DIR` (fora do
   repo — contém CNPJ/valor em texto claro).

### 7. Testes

Tudo no CI é sem browser/rede:
- `test_config.py` — normalizações, erros agregados, `redact()`.
- `test_review.py` — `check_review` puro, fixtures com CNPJ fictício
  (`00.000.000/0001-91`), HTML mínimo escrito à mão (nunca salvar HTML real
  do portal).
- `test_safety.py` — stub de `Page` (duck-typed, zero Playwright real):
  `submit(confirmed=False)` levanta; `preview` nunca chama `submit`; `emit`
  com stdin não-TTY aborta antes de qualquer clique; `emit` com divergência
  aborta antes do prompt.
- `test_no_secrets.py` — varre `bin/`, `tests/`, `README*.md`,
  `.env.example` procurando CNPJ/CPF (11/14 dígitos, padrão mascarado), com
  allowlist dos fictícios de teste.
- `tests/integration/test_live_wizard.py` — `@pytest.mark.integration`,
  skip sem `NFSE_LIVE=1`, aponta pra produção restrita, para em
  `read_review` (nunca submete). Excluído do CI por `addopts` (já
  configurado no pyproject.toml).

### 8. README

Corpo (o header/badges o tscaf já cuidou): o problema (MEI preenchendo
NFS-e à mão), a pesquisa (por que não API — certificado A1 pago em todo
gateway/API oficial; portal web aceita gov.br grátis pra MEI), setup, seção
de segurança em destaque (dry-run default, dupla confirmação, recusa
non-TTY, produção restrita como default), limitações (2FA não
automatizável, sessão curta, seletores podem quebrar).

### 9. Ordem de implementação sugerida

1. `nfse_config.py` + `tests/test_config.py` (puro, fecha o contrato de
   dados antes de tocar em browser).
2. `nfse_browser.py` (perfil persistente, `is_session_expired`, helpers) +
   `nfse_emit.py login`. Validar login manual antes de preencher algo.
3. `nfse_selectors.py` + `fill_pessoas` (a etapa mais frágil).
4. `fill_servico`, `fill_tributacao`.
5. `read_review` + `check_review` + `tests/test_review.py`.
6. `nfse_submit.py` + porta de confirmação + `tests/test_safety.py`.
7. `tests/test_no_secrets.py`, `.env.example`, corpo dos READMEs, CHANGELOG.
8. Ensaio ponta a ponta em produção restrita (incluindo o clique final), só
   depois `preview` em produção real.

### 10. Fora de escopo (deliberado)

- Parsear XMLs de notas antigas pra semear `.env` automaticamente — feature
  futura (`nfse_emit.py seed --from-xml`, só imprime no stdout, nunca
  escreve `.env` sozinho), depois do primeiro `emit` real bem-sucedido.
- Agendamento (systemd timer) — incompatível de propósito com a recusa de
  emitir sem TTY.

---

## Part 2 — Field-by-field map from the live walkthrough

Mapeado ao vivo contra a conta real do usuário no Emissor Nacional
(https://www.nfse.gov.br/EmissorNacional), validado contra um XML de nota
anterior. Rótulos em pt-BR são os literais vistos na tela — usar como texto
pra `get_by_label`/`get_by_role(name=...)`.

### Login (`/EmissorNacional/Login`)

3 opções: usuário/senha, certificado digital, "Entrar com gov.br". MEI usa
gov.br (grátis, com 2FA — **não automatizável**). Sessão expira; um reload
já causou redirect pra `/Login?ReturnUrl=...` durante o mapeamento.

### Etapa 1 — Pessoas (`/EmissorNacional/DPS/Pessoas`)

1. Radio, label exato: **"Preencher as informações IBS/CBS?"** → marcar
   **"Não"**.
2. Campo data: **"Data de Competência"** (date picker com ícone de
   calendário) → preencher com data atual.
3. Radio **"Você irá emitir esta NFS-e como?"** → já vem **"Prestador/
   Fornecedor"** selecionado por default, nenhuma ação.
4. Depois dos 2 primeiros campos preenchidos, os campos do emitente
   (**Município**, **CNPJ**, **Razão Social**, **"Opção no Simples
   Nacional"**) auto-populam sozinhos a partir da conta logada — não
   digitar. ATENÇÃO: nessa etapa o carregamento da lista de municípios já
   falhou uma vez com um modal "Mensagem do Sistema" / texto **"Não foi
   possível recuperar a lista de municípios."**, com botão "Fechar" — só um
   reload completo da página destravou. É aqui que `retry_step` entra.
5. Radio **"A operação se trata de uma compra governamental?"** → **"Não"**.
6. Seção **"Tomador/Adquirente do Serviço"**: radio **"Onde está localizado
   o estabelecimento/domicílio?"** → default **"Brasil"**, nenhuma ação.
   Ao lado do campo **"CPF/CNPJ"** tem 2 ícones: uma lupa (busca por CNPJ na
   Receita) e um ícone de **grupo de pessoas** que abre um modal
   **"HISTÓRICO"** — "A lista abaixo contém o nome/razão social de todas as
   pessoas que você informou nas últimas NFS-e emitidas." — com uma tabela
   (colunas CPF/CNPJ, Nome/Razão Social) de radio-select por linha e um
   botão **"Importar"**. Selecionar a linha certa (ancorar pelo texto do
   CNPJ, nunca por índice) e clicar Importar preenche automaticamente:
   CPF/CNPJ, Nome/Razão Social, CEP, Bairro, Logradouro, Número,
   Complemento. **Esse é o caminho primário** pro caso de uso (tomador fixo
   todo mês). Fallback se a lista vier vazia (é o caso da produção
   restrita) ou a linha não existir: digitar o CNPJ no campo — o portal
   auto-popula a Razão Social a partir da base da Receita.
7. Seção **"Destinatário do Serviço"**: radio **"Para fins de apuração do
   IBS/CBS, o destinatário é o próprio adquirente?"** → **"Sim"**.
8. Seção **"Intermediário do Serviço"**: radio **"Onde está localizado o
   estabelecimento/domicílio?"** → já vem **"Intermediário não informado"**
   selecionado, nenhuma ação.
9. Botão **"Avançar"** no fim da página.

### Etapa 2 — Serviço (`/EmissorNacional/DPS/Servico?idr=<opaco>`)

1. Seção **"Local do Fornecimento/Prestação do Serviço"**: campo **"País"**
   já vem "Brasil"; campo **"Município"** é select buscável — clicar, digitar
   nome da cidade (ex: "Belo Horizonte"), esperar dropdown, clicar na opção
   com formato `"Cidade/UF"` (ex: "Belo Horizonte/MG").
2. Seção **"Serviço/Fornecimento Prestado"**:
   - **"Código de Tributação Nacional"**: select buscável, digitar o código
     numérico (ex: "170201"), esperar dropdown, clicar na opção (formato
     `"NN.NN.NN - Descrição."`, ex: "17.02.01 - Datilografia, digitação,
     estenografia e congêneres.").
   - Radio **"O serviço/fornecimento prestado é um caso de: imunidade,
     exportação de serviço ou não incidência do ISSQN?"** → **"Não"**.
   - **"Item da NBS correspondente ao serviço/fornecimento prestado"**: TEM
     asterisco vermelho (parece obrigatório) mas **é opcional de verdade**
     — testado deixar em branco, o wizard avança normalmente e a tela final
     de revisão mostra "Não informado" sem bloquear nada. **Pular esse
     campo deliberadamente** (deixar um comentário no código explicando,
     senão alguém "conserta" isso depois achando que é bug).
   - **"Descrição do Serviço/Fornecimento"** (textarea, obrigatório de
     verdade): texto livre.
   - Seção **"Informações Complementares"** (número doc. responsabilidade
     técnica, documento de referência, informações complementares, número
     de pedido/OC/projeto B2B): todos opcionais, pular.
3. Botão **"Avançar"**.

### Etapa 3 — Valores/Tributação (`/EmissorNacional/DPS/Tributacao?idr=<opaco>`)

1. **"Valor da operação/serviço prestado"**: campo com máscara `R$`,
   preencher com o valor (usar `fill_masked`, testado que digitação simples
   às vezes não gruda no campo mascarado).
2. Campos **"Valor recebido pelo intermediário"**, **"Desconto
   incondicionado"**, **"Desconto condicionado"**: desabilitados/opcionais,
   pular.
3. Seção **"Tributação Municipal"**: mostra aviso "As informações de
   Tributação Municipal abaixo não podem ser alteradas pois o tributo
   (ISSQN) será apurado pelo Simples Nacional." Campos **"Tributação do
   ISSQN sobre o serviço prestado"** ("Operação Tributável") e **"Regime
   Especial de Tributação"** ("Nenhum") ficam readonly. Radios (todos já
   vêm **"Não"** selecionado por default — confirmar, não mudar):
   - "A exigibilidade do recolhimento do ISSQN devido nesta operação está
     suspensa?"
   - "Há retenção do ISSQN pelo Tomador ou pelo Intermediário?"
   - "Este serviço prestado está amparado por algum benefício municipal?"
   - "Será aplicado algum tipo de Dedução/Redução à base de cálculo do
     ISSQN?"
4. Seção **"Tributação Federal"**: aviso "não podem ser alteradas pois os
   tributos relacionados serão apurados pelo Simples Nacional" — campos
   (Situação Tributária PIS/COFINS, Tipo de retenção PIS/COFINS/CSLL, IRRF,
   Contribuições Sociais - Retidas, Contribuição Previdenciária - Retida)
   desabilitados, nenhuma ação.
5. Seção **"IBS/CBS"**: desabilitada porque a Etapa 1 marcou "Não" pra
   "Preencher informações IBS/CBS" — nenhuma ação.
6. Seção **"Valor Aproximado dos Tributos"**: radio já vem **"Não informar
   nenhum valor estimado para os Tributos (Decreto 8.264/2014)"**
   selecionado (as outras opções são "Preencher os valores monetários em
   cada NFS-e emitida" e "Configurar os valores percentuais
   correspondentes") — confirmar, não mudar.
7. Botão **"Avançar"**.

### Etapa 4 — Emitir NFS-e (`/EmissorNacional/DPS/EmitirNFSe?idr=<opaco>`)

Tela de revisão/resumo — SEM formulários, só leitura, organizada em seções
com um botão "Editar X" cada (Editar Pessoas / Editar Serviço / Editar
Tributação) e, no fim, a seção **"PRÉVIA DOS VALORES DA NFS-E"** com:
"ISSQN calculado" (Serviço prestado, Base de cálculo, Alíquota aplicada,
ISSQN — os 3 últimos ficam "-" quando apurado pelo Simples Nacional),
"PIS - Débito Apuração Própria", "COFINS - Débito Apuração Própria",
"Imposto de Renda Retido na Fonte (IRRF)", "Contribuições Sociais -
Retidas", "Contribuição Previdenciária - Retida" (todos R$ 0,00 no caso
Simples Nacional sem retenção), e por fim **"Valor líquido da NFS-e"**
(Serviço prestado / Valor total de tributos retidos / Valor líquido da
NFS-e). Botão final: **"Emitir NFS-e"** — é aqui, e só aqui, que
`nfse_submit.py` deve agir, e só com `confirmed=True`.

Essa é a tela pra `read_review()` extrair o `ReviewSummary` inteiro.

### Notas gerais de robustez observadas

- O site é lento/instável: vários `screenshot`/cliques deram timeout de CDP
  na primeira tentativa e funcionaram na segunda — sugere que o site em si
  trava a UI thread periodicamente, não é problema do driver. Vale timeout
  generoso (o `NFSE_TIMEOUT_MS=20000` do `.env.example` é um ponto de
  partida razoável, pode precisar mais).
- Alguns campos "Selecione..." (select buscável) só abrem a caixa de busca
  depois de clicados — não confiar em `fill()` direto, sempre
  clicar-esperar-digitar-esperar-clicar-na-opção (é o que `select_searchable`
  encapsula).

---

## Part 3 — Live run log (2026-09-01, produção real, nota nº 4)

Emissão real feita manualmente via Claude in Chrome (não pelo script — ainda
em ajuste), seguindo exatamente o mapeamento da Parte 2, pra emitir a nota
de competência 09/2026 no prazo. Serve como confirmação de que o mapeamento
está correto contra o site real, com os ajustes/achados abaixo.

### Diffs em relação ao mapeamento original (Parte 2)

- **"Destinatário do Serviço" (pergunta do IBS/CBS) não é obrigatório de
  verdade**, apesar de não ter asterisco mas parecer parte do fluxo
  obrigatório: deixei os dois radios ("Sim"/"Não") sem marcar e cliquei
  "Avançar" mesmo assim — o wizard avançou normalmente pra etapa Serviço.
  Não precisa clicar em nada nessa seção quando "Preencher as informações
  IBS/CBS?" já foi "Não" na etapa Pessoas.
- **Extensão do Claude in Chrome caiu/desconectou 2x** durante a sessão
  (não é instabilidade só do portal — a ponte browser↔agente também
  falhou). Sintoma: `tabs_context_mcp` retorna "Browser extension is not
  connected". Solução: usuário alternar pra janela do Chrome (acorda a
  extensão) ou reabrir o Chrome; depois `tabs_context_mcp` volta a
  funcionar. Isso não é um problema do Playwright (que não depende dessa
  extensão), mas registra que a sessão inteira de login/preenchimento pode
  precisar ser refeita do zero se a ponte cair no meio.
- **A sessão expira rápido**: em pelo menos uma ocasião, um simples reload
  da página `/DPS/Pessoas` (sem nem ter passado muito tempo) já redirecionou
  pra `/Login?ReturnUrl=...`. Confirma a recomendação da Parte 1 de checar
  `is_session_expired` depois de toda navegação/reload, não só uma vez no
  início.
- **O clique em "Avançar" às vezes não navega instantaneamente** mesmo sem
  erro visível — a URL só mudou depois de um `wait` + nova checagem. Vale
  não tratar "URL não mudou logo após o clique" como falha definitiva antes
  de dar um retry/wait curto.
- **O PDF (DANFSe) da nota nº 4 tem um layout diferente das notas 1-3**:
  agora mostra campos "Valor Total Apurado - IBS" / "Valor Total Apurado -
  CBS" que não existiam antes (provavelmente atualização do template do
  portal por causa da reforma tributária, mesmo com "Preencher as
  informações IBS/CBS?" = Não). Não é um erro de preenchimento — é só o
  portal atualizando o layout do documento entre uma emissão e outra. Vale
  não assumir que o layout do PDF é estático ao escrever qualquer parsing
  futuro de DANFSe.

### Resultado final (dados reais, não hardcoded no código)

Nota nº 4 emitida com sucesso: competência 01/09/2026, tomador WHITE WALL
TECNOLOGIA LTDA, valor R$ 2.000,00, mesmo padrão das 3 notas anteriores. PDF
e XML baixados, renomeados pro padrão `<N> + 66.544.208 IAN PATRICK DA
COSTA SOARES.{pdf,xml}` e movidos pra
`~/Documents/profissionais/wiv/notasfiscais/` (fora deste repo — dado
pessoal). Conferido depois: os 4 pares PDF/XML têm `nNFSe` sequencial
(1-4), mesmo tomador, mesmo valor (R$ 2.000,00) e competências mensais em
sequência (jun→jul→ago→set/2026) — nenhuma inconsistência entre PDF e XML
de nenhum dos 4.

Essa nota nº 4 é o novo XML de referência mais atual pra validar o `.env`
e os testes (`tests/test_review.py` etc.) contra dados reais, se precisar
comparar de novo.
