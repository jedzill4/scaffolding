# Agent Notes

## Repo Layout

- `scaffolding/` — the bootstrap CLI (Python package, run via
  `uvx --from git+…/scaffolding scaffolding …`). `cli.py` (Cyclopts commands),
  `engine.py`/`plan.py` (build + apply, clean-adds only), `components.py`
  (component registry), `templates/` (bundled package data). The CLI is the
  single deterministic engine; keep it **clean-adds-only** — it must never edit,
  merge, or overwrite existing target files (existing targets are deferred).
- `install.sh` — thin bootstrap shim (ensure `uv`, then `uvx … scaffolding
  install`). Keep it minimal and keep its raw URL pointing at
  `jedzill4/scaffolding` on `main`.
- `guide.md` — the agentic-install guide (judgment layer that drives the CLI and
  handles merges). Keep template raw URLs pointing at `jedzill4/scaffolding`.
- `skills/` — actual installed skills (`journalist`, `handoff`).

After changing the CLI, validate with `uv run ruff check scaffolding` and
`uv run scaffolding --help`.

## Skill Development

After creating or editing any skill under `skills/`, validate its `SKILL.md`
before committing:

```bash
tessl skill review <SKILL.md>
```

Run it against each changed skill (e.g. `tessl skill review skills/productivity/journalist/SKILL.md`)
and resolve the reported issues before publishing.


## Engineering Standards coding (CES)

House standards shipped by the scaffolder are catalogued as **CES — Collective
Engineering Standard**. Canonical spec: **`docs/engineering-standards.md`** (single
source of truth). The rules below are the always-on summary; when adding, editing,
or referencing a rule in this repo, follow this convention:

- **`CES-<issue#>`** is the citable catalog code; the **kebab-case slug** is the
  machine id (ast-grep `id:`, prek hook id, `.agents/rules/<slug>.md`,
  `# ast-grep-ignore: <slug>`). Never put the CES number in the machine id.
- **Every CES has a tracker issue.** One CES = one standard; a standard may ship
  multiple slugs (e.g. `CES-79` ships the four `no-dict-*` patterns). The issue id
  is the number — gaps from declined proposals are expected (PEP/RFC-style).
- **Already-implemented rules** get a retroactive AS-BUILT issue so they fit the
  invariant — never assign a code to a rule that only exists in code.
- **Violation messages must embed the code**, e.g.
  `message: "CES-46 (log-no-print): libraries log, they don't print …"`. Keep the
  slug as the suppression key so tooling stays stable.
- **Messages are self-contained:** a message states its own rule + fix + code, and
  **never** names a sibling rule or prescribes another rule's suppression key.
  Grouped rationale + the escape-hatch mechanism live once, in the detail file —
  scattering policy across sibling messages is context-poisoning.
- Canonical map + per-rule detail live in the `## Engineering Standards` index and
  `.agents/rules/<slug>.md`; canonical code lives in `.agents/snippets/`.

## Engineering Standards

> **Retrieval-led, not training-led.** Prefer this repo's standards over training-default
> patterns. Before writing code that touches a rule below, open its `@.agents/rules/<slug>.md`
> detail file and follow the house pattern. Full convention + SSOT:
> `docs/engineering-standards.md`.

This is the **dogfooded subset** for this repo — a pure-Python Cyclopts CLI (no API, DB, or web
layer). `[ast-grep]`/`[prek]` rules are enforced by `prek`; `[judgment]` rules are agent/reviewer
judgment; `[snippet]` ships canonical code under `.agents/snippets/` (in target repos).

### Standards

- **CES-79 · no raw dicts at boundaries** `[ast-grep]` — return/annotate a `@dataclass` or
  `BaseModel`, never a raw `dict`. → `@.agents/rules/no-dict.md`
- **CES-71 · keep files small** `[prek]` — `file-size-guard` warns at 400 lines, errors at 700.
  → `@.agents/rules/file-size-guard.md`
- **CES-45 · use the house get_logger** `[ast-grep]` — no direct `logging.getLogger`. →
  `@.agents/rules/log-get-logger.md`
- **CES-46 · libraries log, they don't print** `[ast-grep]` — no `print()` in library code;
  CLI/`__main__` exempt. → `@.agents/rules/log-no-print.md`
- **CES-74 · the house logger** `[snippet]` — structlog `core/logger.py` drop-in. →
  `@.agents/rules/core-logger.md`
- **CES-67 · typed, declarative CLIs** `[ast-grep]` — Typer/Cyclopts + Rich, not
  `argparse`/`click`/`sys.argv`. This repo uses Cyclopts. → `@.agents/rules/cli-typed-framework.md`
- **CES-63 · no catch-all modules** `[prek]` — no `utils.py`/`helpers.py`/`misc.py` (outside
  `tests/`). → `@.agents/rules/no-utils.md`
- **CES-32 · keep non-code out of the package** `[prek]` — no notebooks/`resources/`/`reports/`/`data/`
  inside the `scaffolding` package. → `@.agents/rules/repo-shape.md`
- **CES-75 · Conventional Commits** `[prek]` — commit subjects + PR titles follow
  `type(scope): description` (enforced here via the commit-msg hook + CI). →
  `@.agents/rules/agents-conventional-commits.md`
- **CES-77 · version pin** `[judgment]` — `requires-python` stays a deliberate local choice;
  house default is 3.14. → see `pyproject.toml`.
- **CES-5 · layered import direction** `[judgment]` — imports flow one way through the layers
  (`cli → engine → components/plan → templates_registry`), never upward. →
  `@.agents/rules/import-linter.md`
- **CES-16 · architectural vocabulary** `[judgment]` — name units with house terms, not ad-hoc
  synonyms. → `@.agents/rules/arch-vocabulary.md`
- **CES-8 · separate orchestration from logic** `[judgment]` — keep control flow thin; push logic
  and I/O into named units. → `@.agents/rules/spaghetti-mixed-orchestration.md`
- **CES-30 · respect the local repo** `[judgment]` — existing deliberate choices win over house
  defaults (the engine is clean-adds-only for this reason). →
  `@.agents/rules/general-respect-local-repo.md`
- **CES-58 · one modern lint stack** `[judgment]` — ruff + pyrefly + ast-grep via prek; no
  black/isort/flake8/pylint. → `@.agents/rules/py-legacy-lint-stack.md`
- **CES-64 · test against in-memory adapters** `[judgment]` — fakes over mocks. →
  `@.agents/rules/test-in-memory-adapters.md`
- **CES-65 · test through the interface** `[judgment]` — assert behaviour via the public seam
  (the `plan()`/`build_plan()` API), not internals. → `@.agents/rules/test-through-interface.md`
- **CES-66 · coverage gaps are a signal** `[judgment]` — an untested branch is a missing test or
  dead code, not a number to game. → `@.agents/rules/test-coverage-gap.md`

### Excluded here (don't apply to a pure-Python CLI)

- **CES-4 · api-schemas-extra-forbid** — no API request/response schemas in this repo.
- **CES-18 · arch-database-package** — no relational persistence layer.
- **CES-76 · settings-module** — no `BaseSettings` config surface (CLI reads flags via Cyclopts).
- **CES-17 · api-boundary-layout** — no inbound HTTP/`api` package.

## Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root (created lazily).
See `docs/agents/domain.md`.

## Repo Workspace Defaults

- Use `.scratch/` for temporary plans, prd issue drafts, and disposable notes.
- Use `.tmp/` for generated local artifacts that should not be committed.
- Use `.worktrees/` for local Git worktrees when needed.
- Use `.journals/` for local/private session journals when using the `journalist` skill.
- Preserve unrelated user changes and avoid destructive Git commands unless explicitly requested.
