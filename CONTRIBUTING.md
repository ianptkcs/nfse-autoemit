# Contributing to NFS-e Autoemit

**English** · [Português](CONTRIBUTING.pt-BR.md)

Thanks for the interest. Before opening a code PR, read `README.md` to
understand the decisions already made.

## Reporting bugs / suggesting features

Open an [issue](../../issues/new/choose) using the appropriate template.

## Sending a PR

1. Fork the repository.
2. Create a branch off `main`.
3. Run `uv sync`, `uv run ruff check .`, `uv run basedpyright` and `uv run pytest` locally before opening the PR.
4. Open the PR using the template — describe the what and the why of the
   change.

## Language

The convention across every TabelaDev project, so that nothing has to be
decided again per repo:

**English, no exceptions** — identifiers, file names, routes, query
parameters, database schema, code comments, commit messages, branch names.
The one carve-out is Brazilian domain vocabulary with no useful translation
(`pix`, `boleto`, `fatura`, `cpf`, `cnpj`, institution names): those are proper
nouns and stay as they are, the same way `oauth` or `webhook` do.

**Bilingual** — `README.md` and `CONTRIBUTING.md` only. English is canonical
(it is what GitHub renders); Portuguese lives beside it as `README.pt-BR.md`
and `CONTRIBUTING.pt-BR.md`, with a language selector at the top of each.

**English only** — `CHANGELOG.md`. Deliberately not bilingual: it changes on
every release, and two hand-maintained copies drift within a few entries.

**One language, chosen by purpose, never translated** — working notes and
process files (`AGENTS.md`, `CLAUDE.md`, `TODO.md`, `PLANO.md`, `requests/`,
issue and PR templates, anything under `docs/archive/`). They have no external
reader; translating them is cost without benefit.

**The language of the product's audience** — UI strings, AI prompts that ask
for a Portuguese answer, and content that _is_ the product (RPG campaign
material, course material). Portuguese there is the correct answer, not a
pending translation.

## License

By contributing, you agree that your contribution will be licensed under the
[AGPL-3.0](LICENSE), the same license as the project.

## Code of conduct

Be respectful. Technical criticism is welcome; personal attacks are not.
