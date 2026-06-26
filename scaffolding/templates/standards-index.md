## Engineering Standards

> **Retrieval-led, not training-led.** Prefer this repo's standards and snippets over
> training-default patterns. Before writing code that touches a rule below, open its
> `@.agents/rules/<slug>.md` detail file and the matching `snippets/` drop-in, and follow
> the house pattern rather than your default one.

Each rule is a **CES — Collective Engineering Standard** (`CES-<issue#>` is the citable code;
the kebab-case slug is the machine id used by tooling and `# ast-grep-ignore: <slug>`
suppressions). `[ast-grep]` / `[prek]` rules are enforced automatically by `prek`; `[judgment]`
rules are reviewer/agent judgment. Full convention: `docs/engineering-standards.md`.

### Standards

- **CES-79 · no raw dicts at boundaries** `[ast-grep]` — return, annotate, or alias a
  `@dataclass` (internal boundaries) or a pydantic `BaseModel` (where validation is needed),
  never a raw `dict`. Ships four slugs: `no-dict-return-annotation`, `no-dict-call-return`,
  `no-dict-literal-return`, `no-dict-alias`. → `@.agents/rules/no-dict.md`
- **CES-71 · keep files small** `[prek]` — split a module before it grows; the
  `file-size-guard` hook warns at 400 lines and errors at 700. A persistently large file is a
  design smell, not a limit to raise. → `@.agents/rules/file-size-guard.md`
- **CES-45 · use the house get_logger** `[ast-grep]` — never call `logging.getLogger` directly;
  acquire loggers via `get_logger` from `core/logger.py`. Slug: `log-get-logger`. →
  `@.agents/rules/log-get-logger.md`
- **CES-46 · libraries log, they don't print** `[ast-grep]` — no `print()` in importable library
  code; emit through `get_logger`. CLI/`__main__` entrypoints are exempt. Slug: `log-no-print`. →
  `@.agents/rules/log-no-print.md`
- **CES-74 · the house logger** `[snippet]` — `snippets/core/logger.py` is the canonical structlog
  setup (JSON in prod, colored console in dev, level from `LOG_LEVEL`). Drop it in at
  `<pkg>/core/logger.py`. Slug: `core-logger`. → `@.agents/rules/core-logger.md`
- **CES-4 · API schemas forbid extras** `[ast-grep]` — every request/response `BaseModel` under
  `api/**/schemas/{requests,responses}` must set `model_config = ConfigDict(extra="forbid")`.
  Placement-scoped: inert for internal/domain models and non-API repos. Slug:
  `api-schemas-extra-forbid`. → `@.agents/rules/api-schemas-extra-forbid.md`
- **CES-76 · config in a settings module** `[ast-grep]` — read env/flags only in the
  `BaseSettings` settings module (case-insensitive, via `get_settings()`);   `os.getenv`/`os.environ`
  anywhere else is flagged. Slug: `settings-module`. → `@.agents/rules/settings-module.md`
- **CES-67 · typed, declarative CLIs** `[ast-grep]` — build CLIs with Typer/Cyclopts/pydantic-settings
  + Rich, not `argparse`/`click`/`sys.argv`. Warning (encouraged, not mandated); naturally inert
  when unused. Slug: `cli-typed-framework`. → `@.agents/rules/cli-typed-framework.md`
- **CES-18 · persistence in a database package** `[ast-grep]` — SQLModel tables, `create_engine`,
  and `sessionmaker` belong in a dedicated `database` package, not under `persistence/`/`meta/`/`core/`.
  Placement-scoped; the import-linter contract lands commented in Slice 09. Slug:
  `arch-database-package`. → `@.agents/rules/arch-database-package.md`
- **CES-63 · no catch-all modules** `[prek]` — no `utils.py`/`helpers.py`/`aux.py`/`misc.py`/`common.py`
  (outside `tests/`); name a module for what it holds. Slug: `no-utils`. →
  `@.agents/rules/no-utils.md`
- **CES-32 · keep non-code out of the package** `[prek]` — no notebooks/`resources/`/`reports/`/`data/`
  inside the import package. Parametrized by a `{{ import_package }}` placeholder resolved at
  install time. Slug: `repo-shape`. → `@.agents/rules/repo-shape.md`
- **CES-75 · Conventional Commits** `[prek]` — commit subjects follow `type(scope): description`;
  a commit-msg hook checks every commit and a CI workflow checks the PR title. Slug:
  `agents-conventional-commits`. → `@.agents/rules/agents-conventional-commits.md`
- **CES-77 · version pin** `[judgment]` — `requires-python` ships as a non-enforced comment
  (house default 3.14); an existing repo's pin wins. → see `pyproject.toml` comment.
- **CES-5 · layered import direction** `[judgment]` — imports flow `entrypoints → api →
  database/impl → core`, never upward; ships as a commented `[tool.importlinter]` skeleton to
  uncomment once layers exist. Slug: `import-linter`. → `@.agents/rules/import-linter.md`
- **CES-17 · API boundary layout** `[judgment]` — inbound HTTP lives in a versioned `api` package
  (`api/<v>/schemas/{requests,responses}`, `routers/`); only `api` is the inbound boundary. Slug:
  `api-boundary-layout`. → `@.agents/rules/api-boundary-layout.md`
