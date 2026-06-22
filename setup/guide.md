# Setup Repo — Agentic Install Guide

This is a one-time bootstrap guide, not an installed skill. Point an agent at the
raw URL of this file and have it follow every step:

`https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/guide.md`

For a brand-new/empty repo you can skip the agent and run the deterministic
installer directly (clean adds only; it refuses to touch existing files):

```bash
curl -fsSL https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/install.sh | bash
```

For an existing working repo, prefer the agentic path: the installer does only
the safe clean-adds and defers every merge/conflict to you (the agent), per the
rules below.

Prepare an existing project repo with the small defaults I usually want before active work starts. Keep this minimal: do not scaffold application code, install dependencies, or add language-specific tooling unless the user asks.

## Workflow

1. Inspect the repo root for existing `.gitignore`, `.opencode/`, `opencode.json`, `opencode.jsonc`, `prek.toml`, `AGENTS.md`, `CLAUDE.md`, `.env.schema`, and any `.env*` files.
2. Decide whether this is a clean setup (new/empty repo) or a migration into an existing working repo. See [New vs. Existing Repos (Migration)](#new-vs-existing-repos-migration). For a migration, present the installation plan and get the user's decision before writing anything beyond inspection.
3. Preserve existing content. Only add missing files, missing lines, or missing config keys. Never delete, replace, reorder, or simplify existing data without explicit user authorization.
4. Prefer repo-local OpenCode config at `.opencode/opencode.jsonc` so the settings travel with this repo and do not overwrite global config.
5. Add or update the managed workspace section in `AGENTS.md`. Create `AGENTS.md` if it does not exist. Do not edit `CLAUDE.md` during this bootstrap unless the user explicitly asks.
6. Validate that any JSON/JSONC you wrote parses or is accepted by the relevant tool.

## New vs. Existing Repos (Migration)

**New or empty repo (clean setup).** No conflicting `.gitignore`, `.opencode/`, `prek.toml`, `AGENTS.md`, or `.env*`/`.env.schema`? Apply every default directly — write the files, install the skills, and run `varlock init` without negotiation.

**Existing working repo (migration).** When any of those already exist, do not silently change an active project. Inspect first, then present a short installation plan and wait for the user's go-ahead, sorting every change into three buckets:

- **Clean adds** — missing files/entries that only add new content (e.g. a missing `.gitignore` line, a brand-new `.opencode/opencode.jsonc`). Apply once approved.
- **Merges** — additive edits to existing files (missing keys in `opencode.jsonc`, extra `prek.toml` hooks, the `AGENTS.md` section, new `pyproject.toml` tool sections). Show what gets inserted and confirm no collisions.
- **Conflicts** — anything that would remove, replace, reorder, or restructure existing content, or where the user's value differs (e.g. an existing `.env.example`/`.env.schema` `varlock init` might rewrite, a `.gitignore` already handling `.env` differently, clashing permission rules). Never auto-resolve; let the user decide per item and default to the most conservative option.

## Non-Destructive Edits

This bootstrap is additive by default:

- If a file exists, update it in place by adding only the missing entries.
- If a key already exists in `opencode.jsonc`, preserve its current value and merge only missing nested keys or array items.
- If the desired change would require removing, renaming, replacing, or restructuring existing content, stop and ask the user first.
- Do not normalize formatting across the whole file just because it differs from the examples below.

## `.gitignore`

Ensure these workspace-only directories are ignored at the repo root:

```
.env
.tmp/
.scratch/
.worktrees/
.journals/
```

## `prek.toml`

Create or update `prek.toml` only additively. Always include the generic hooks below when missing. Include Python-specific hooks only when the repo has a root `pyproject.toml`, another clear Python layout, or the user asks for Python checks.

Use the bundled templates (the installer fetches these automatically for clean adds; fetch the raw URL yourself when you need the content to merge into an existing file):

- [prek-generic.toml](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/prek-generic.toml) — generic safety and formatting hooks.
- [prek-python.toml](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/prek-python.toml) — Python hooks using `uv`, `ruff`, `pyrefly`, and `ast-grep`.
- [pyproject-template.toml](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/pyproject-template.toml) — starter root Python config with `hatchling`, `ruff`, `pyrefly`, and `pytest` sections.

Assume Python lives at the repo root by default, with `pyproject.toml` at the root. Change paths to a subdirectory such as `backend/` only if the repo layout or user explicitly demands it. Do not add Python-specific hooks to non-Python repos unless the user asks.

If a Python repo has no `pyproject.toml`, create one from `pyproject-template.toml` and replace placeholder project metadata. If `pyproject.toml` already exists, only add missing tool sections and never replace dependencies or project metadata without explicit approval.

## `ast-grep` Rules

The `ast-grep` hook in `prek-python.toml` runs `ast-grep scan`, which requires an `sgconfig.yml` at the repo root pointing at a rule directory. Whenever you add that hook, also scaffold the config and at least one rule, or the hook fails with "No configuration found."

Create both additively, never overwriting existing rules:

- Copy [sgconfig-template.yml](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/sgconfig-template.yml) to the repo root as `sgconfig.yml`. It sets `ruleDirs: [ast-grep/rules]`.
- Copy the starter rules from [templates/ast-grep-rules/](https://github.com/jedzill4/repo-setup/tree/main/setup/templates/ast-grep-rules) into `ast-grep/rules/`. They flag boundary functions that return raw dicts (`no-dict-call-return`, `no-dict-literal-return`, `no-dict-return-annotation`), nudging toward `@dataclass` or pydantic models.

If `sgconfig.yml` already exists, preserve its `ruleDirs` and only add missing rule files. Drop or adjust individual rules to match the repo's conventions when the user asks; treat them as a starting point, not a mandate.

## `.opencode/opencode.jsonc`

Create or update this repo-local OpenCode config from the bundled template [opencode-template.jsonc](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/opencode-template.jsonc). Use JSONC because its comments and trailing commas are intentional. The template sets the `$schema`, the `opencode-sessions-explorer` and `opencode-varlock@latest` plugins, and `permission` rules that deny reading/writing/printing secrets (`.env*`, `*.pem`, `*.key`, `*credentials*`, `varlock.config`) while allowing common safe commands.

Merge it additively into any existing config: add only missing keys, plugin entries, and permission rules, and preserve the user's existing values (see [Non-Destructive Edits](#non-destructive-edits)).

If `opencode-sessions-explorer` is not installed and the user wants it, install/configure it using the project's normal OpenCode plugin workflow. Otherwise keep the config but mention the plugin must be available for the entry to load.

## Varlock Secret Management

Use [Varlock](https://varlock.dev) for environment and secret management so secrets stay out of the repo and out of agent context. The `opencode-varlock@latest` plugin in `.opencode/opencode.jsonc` and the `.env*` permission guards above assume Varlock is installed and the repo carries a committed `.env.schema`.

Install Varlock and scaffold the schema additively. Never overwrite an existing `.env.schema` or `.env` without explicit user approval.

1. **Install as a dependency.** For Node.js/TypeScript projects (Node 22+), add `varlock` and scaffold the schema in non-interactive agent mode so it does not prompt:

   ```bash
   npx varlock init --agent
   ```

   Use the matching package-manager variant when the repo declares one: `pnpm dlx varlock init --agent`, `bunx varlock init --agent`, `vlx varlock init --agent`, or `yarn dlx varlock init --agent`.

   For non-JS repos, or when a global CLI is preferred, install the standalone binary instead and then run the wizard:

   ```bash
   brew install dmno-dev/tap/varlock   # or: curl -sSfL https://varlock.dev/install.sh | sh -s
   varlock init
   ```

   `varlock init` installs `varlock`, scans for existing `.env` files, and creates a root `.env.schema`. It may also offer to remove an existing `.env.example` and add `@type` decorators — review those changes; do not let it delete files the user wants to keep.

2. **Install the Varlock agent skill** so future sessions know how to author `.env.schema` files:

   ```bash
   npx skills add dmno-dev/varlock --agent opencode --yes
   ```

3. **Commit `.env.schema`, never `.env`.** Confirm `.env` is ignored (see [`.gitignore`](#gitignore) above) and that `.env.schema` is tracked. The schema is the source of truth for required variables; real values live only in local `.env` files or the user's secret backend.

## Skill Installation

When setting up agent skills for a repo, install the selected upstream Matt Pocock skills from `mattpocock/skills`, then install this repo's recurring local skills (`journalist`, `handoff`). `setup-repo` itself is intentionally not installed — it is a one-time bootstrap guide, not a skill. Do not vendor or install every upstream skill. Default to OpenCode:

```bash
npx skills add mattpocock/skills --agent opencode --yes --skill diagnose grill-with-docs triage improve-codebase-architecture tdd to-issues to-prd zoom-out prototype grill-me write-a-skill
npx skills add jedzill4/repo-setup --agent opencode --yes --skill journalist handoff
npx skills add dmno-dev/varlock --agent opencode --yes
```

If running from a local checkout of this repo, keep the Matt Pocock command as-is and install local skills with `npx skills add . --agent opencode --yes --skill journalist handoff --full-depth`.

If the repo clearly uses Claude Code or Codex instead of OpenCode, ask before switching `--agent` to `claude-code` or `codex`.

## `AGENTS.md`

The core task of this bootstrap is to write the managed `## Repo Workspace Defaults` section into `AGENTS.md` so the rules apply to every future agent session in this repo. Copy it verbatim from the bundled template [agents-workspace-defaults.md](https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/templates/agents-workspace-defaults.md); it covers the workspace directories (`.scratch/`, `.tmp/`, `.worktrees/`, `.journals/`) and the `### Resource Limits For Heavy Commands` subsection (`systemd-run` memory/CPU caps, `/usr/bin/time -v` logging to `.tmp/logs/`, background execution with a monitor sub-agent, flushed progress output, and tail-only log reading).

If the file already exists, add the section if missing. If the section exists, update only the lines inside it and preserve everything else. If creating a new `AGENTS.md`, add `# Agent Notes` before this section.

For richer agent-skill docs, use Matt Pocock's upstream `setup-matt-pocock-skills` skill if installed.

## Verify

- `.gitignore` contains `.env`, `.tmp/`, `.scratch/`, `.worktrees/`, and `.journals/` exactly once.
- `prek.toml` contains the generic hooks, and Python-specific hooks are present only when appropriate for the repo.
- When the `ast-grep` hook is present, a root `sgconfig.yml` and at least one rule under `ast-grep/rules/` exist so `ast-grep scan` runs cleanly; existing rules were preserved.
- Python repos have a valid `pyproject.toml`; existing project metadata and dependencies were preserved.
- `.opencode/opencode.jsonc` is valid JSONC and includes the schema, plugin, permission, and `mcp` sections.
- Varlock is installed (as a `package.json` dependency or standalone binary) and a root `.env.schema` exists and is tracked by Git, while `.env` files remain ignored.
- Curated skills were installed for the right agent, defaulting to OpenCode unless the user chose another agent, including the `dmno-dev/varlock` skill.
- `AGENTS.md` exists and contains the `## Repo Workspace Defaults` section, including the `### Resource Limits For Heavy Commands` subsection covering `systemd-run` caps, `/usr/bin/time -v` logging to `.tmp/logs/`, background execution with a monitor sub-agent, flushed progress output from our own scripts, and tail-only log reading.
- Existing `AGENTS.md` content outside `## Repo Workspace Defaults` was preserved.
- No existing file content, config key, array item, or comment was removed without explicit user approval.
- For an existing working repo, an installation plan (clean adds / merges / conflicts) was presented and approved before any changes beyond inspection; conflict-bucket items were left untouched unless the user explicitly opted in.
