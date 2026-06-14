---
name: setup-repo
description: "Initialize a repo with personal workspace defaults: gitignore entries, local OpenCode config, AGENTS.md guidance, and optional prek pre-commit hooks. Use when starting a new project, onboarding to a repo, bootstrapping workspace setup, or normalizing a project for day-to-day agent-assisted development."
---

# Setup Repo

Prepare an existing project repo with the small defaults I usually want before active work starts. Keep this minimal: do not scaffold application code, install dependencies, or add language-specific tooling unless the user asks.

## Workflow

1. Inspect the repo root for existing `.gitignore`, `.opencode/`, `opencode.json`, `opencode.jsonc`, `prek.toml`, `AGENTS.md`, and `CLAUDE.md`.
2. Preserve existing content. Only add missing files, missing lines, or missing config keys. Never delete, replace, reorder, or simplify existing data without explicit user authorization.
3. Prefer repo-local OpenCode config at `.opencode/opencode.jsonc` so the settings travel with this repo and do not overwrite global config.
4. Add or update the managed workspace section in `AGENTS.md`. Create `AGENTS.md` if it does not exist. Do not edit `CLAUDE.md` for this skill unless the user explicitly asks.
5. Validate that any JSON/JSONC you wrote parses or is accepted by the relevant tool.

## Non-Destructive Edits

This skill is additive by default:

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

Use the bundled templates:

- [prek-generic.toml](./prek-generic.toml) — generic safety and formatting hooks.
- [prek-python.toml](./prek-python.toml) — Python hooks using `uv`, `ruff`, `pyrefly`, and `ast-grep`.
- [pyproject-template.toml](./pyproject-template.toml) — starter root Python config with `hatchling`, `ruff`, `pyrefly`, and `pytest` sections.

Assume Python lives at the repo root by default, with `pyproject.toml` at the root. Change paths to a subdirectory such as `backend/` only if the repo layout or user explicitly demands it. Do not add Python-specific hooks to non-Python repos unless the user asks.

If a Python repo has no `pyproject.toml`, create one from `pyproject-template.toml` and replace placeholder project metadata. If `pyproject.toml` already exists, only add missing tool sections and never replace dependencies or project metadata without explicit approval.

## `.opencode/opencode.jsonc`

Create or update this repo-local OpenCode config. Use JSONC because comments and trailing commas are intentional.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-sessions-explorer"],
  "permission": {
    "external_directory": {
      "~/.local/share/opencode/**": "allow"
    },
    "skill": {
      "*": "allow"
    }
  },
  "mcp": {}
}
```

If `opencode-sessions-explorer` is not installed and the user wants it, install/configure it using the project's normal OpenCode plugin workflow. Otherwise keep the config but mention the plugin must be available for the entry to load.

## `AGENTS.md`

Create or update this managed section in `AGENTS.md`. If the file already exists, add the section if missing. If the section exists, update only the lines inside this section and preserve everything else.

If creating a new `AGENTS.md`, add `# Agent Notes` before this section.

```markdown
## Repo Workspace Defaults

- Use `.scratch/` for temporary plans, issue drafts, and disposable notes.
- Use `.tmp/` for generated local artifacts that should not be committed.
- Use `.worktrees/` for local Git worktrees when needed.
- Use `.journals/` for local/private session journals when using the `journalist` skill.
- Preserve unrelated user changes and avoid destructive Git commands unless explicitly requested.
```

For richer agent-skill docs, run the `setup-skills` skill after this one.

## Verify

- `.gitignore` contains `.env`, `.tmp/`, `.scratch/`, `.worktrees/`, and `.journals/` exactly once.
- `prek.toml` contains the generic hooks, and Python-specific hooks are present only when appropriate for the repo.
- Python repos have a valid `pyproject.toml`; existing project metadata and dependencies were preserved.
- `.opencode/opencode.jsonc` is valid JSONC and includes the schema, plugin, permission, and `mcp` sections.
- `AGENTS.md` exists and contains the `## Repo Workspace Defaults` section.
- Existing `AGENTS.md` content outside `## Repo Workspace Defaults` was preserved.
- No existing file content, config key, array item, or comment was removed without explicit user approval.
