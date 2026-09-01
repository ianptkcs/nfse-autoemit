# Contribuindo com o NFS-e Autoemit

[English](CONTRIBUTING.md) · **Português**

Obrigado pelo interesse. Antes de abrir um PR de código, dá uma olhada no
`README.md` pra entender as decisões já tomadas.

## Reportando bugs / sugerindo features

Abra uma [issue](../../issues/new/choose) usando o template apropriado.

## Enviando um PR

1. Fork o repositório.
2. Crie uma branch a partir de `main`.
3. Rode `uv sync`, `uv run ruff check .`, `uv run basedpyright` and `uv run pytest` localmente antes de abrir o PR.
4. Abra o PR usando o template — descreva o quê e o porquê da mudança.

## Idioma

A convenção vale pra todo projeto do TabelaDev, pra isso não ser decidido de
novo em cada repo:

**Inglês, sem exceção** — identificadores, nomes de arquivo, rotas, query
params, schema de banco, comentários de código, mensagens de commit e nomes de
branch. A única ressalva é vocabulário de domínio brasileiro sem tradução útil
(`pix`, `boleto`, `fatura`, `cpf`, `cnpj`, nomes de instituição): são nomes
próprios e ficam como estão, igual `oauth` ou `webhook`.

**Bilíngue** — só `README.md` e `CONTRIBUTING.md`. O inglês é o canônico (é o
que o GitHub renderiza); o português fica ao lado como `README.pt-BR.md` e
`CONTRIBUTING.pt-BR.md`, com um seletor de idioma no topo de cada um.

**Só inglês** — `CHANGELOG.md`. Deliberadamente não bilíngue: muda a cada
release, e duas cópias mantidas à mão dessincronizam em poucas entradas.

**Um idioma só, escolhido por propósito, nunca traduzido** — anotação de
trabalho e arquivos de processo (`AGENTS.md`, `CLAUDE.md`, `TODO.md`,
`PLANO.md`, `requests/`, templates de issue e PR, qualquer coisa em
`docs/archive/`). Não têm leitor externo; traduzir é custo sem retorno.

**O idioma do público do produto** — strings de UI, prompts de IA que pedem
resposta em português, e conteúdo que _é_ o produto (material de campanha de
RPG, material de curso). Português ali é a resposta certa, não uma tradução
pendente.

## Licença

Ao contribuir, você concorda que sua contribuição será licenciada sob a
[AGPL-3.0](LICENSE), a mesma licença do projeto.

## Código de conduta

Seja respeitoso. Críticas técnicas são bem-vindas; ataques pessoais não.
