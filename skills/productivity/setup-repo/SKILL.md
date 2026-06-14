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

## Skill Installation

When setting up agent skills for a repo, install the selected upstream Matt Pocock skills from `mattpocock/skills`, then install this repo's two local skills. Do not vendor or install every upstream skill. Default to OpenCode:

```bash
npx skills add mattpocock/skills --agent opencode --yes --skill diagnose grill-with-docs triage improve-codebase-architecture tdd to-issues to-prd zoom-out prototype grill-me write-a-skill
npx skills add jedzill4/skills --agent opencode --yes --skill setup-repo journalist handoff
```

If running from a local checkout of this skills repo, keep the Matt Pocock command as-is and install local skills with `npx skills add . --agent opencode --yes --skill setup-repo journalist handoff --full-depth`.

If the repo clearly uses Claude Code or Codex instead of OpenCode, ask before switching `--agent` to `claude-code` or `codex`.

## `AGENTS.md`

The core task of this skill is to write the managed section below into `AGENTS.md` so the rules apply to every future agent session in this repo. If the file already exists, add the section if missing. If the section exists, update only the lines inside this section and preserve everything else. If creating a new `AGENTS.md`, add `# Agent Notes` before this section.

Write this block verbatim:

```markdown
## Repo Workspace Defaults

- Use `.scratch/` for temporary plans, issue drafts, and disposable notes.
- Use `.tmp/` for generated local artifacts that should not be committed.
- Use `.worktrees/` for local Git worktrees when needed.
- Use `.journals/` for local/private session journals when using the `journalist` skill.
- Preserve unrelated user changes and avoid destructive Git commands unless explicitly requested.

### Resource Limits For Heavy Commands

Run computationally expensive commands (heavy builds, full test suites, data jobs, memory-hungry tooling) under `systemd-run` so a runaway process cannot exhaust the machine:

- Cap memory with `MemoryMax` (hard limit; process is killed if exceeded) and disable swap thrashing with `MemorySwapMax=0`.
- Cap CPU with `CPUQuota` (e.g. `400%` = up to 4 cores).
- Use a transient user scope (no root needed). If `systemd-run` is unavailable, fall back to `ulimit -v` for a memory cap.

Measure and log wall time and peak memory with `/usr/bin/time -v`, appending to `.tmp/logs/<command>/<date>_wall-stats.log`. Read the latest log before re-running to estimate limits instead of guessing:

```bash
cmd=build; ts=$(date +%Y-%m-%dT%H-%M-%S)
log=.tmp/logs/$cmd/${ts}_wall-stats.log; mkdir -p ".tmp/logs/$cmd"
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=400% \
  /usr/bin/time -v -o "$log" <command>
```

Run long commands in the background with a saved PID so they are not tied to the agent tool timeout, and delegate polling to a cheap monitor sub-agent (e.g. Haiku) that runs a `while kill -0 <pid>; do sleep <n>; done` loop and reports only the final exit status, output tail, and stats log path. This keeps the main session from being poisoned by repeated status checks.

```bash
( systemd-run --user --scope -p MemoryMax=4G -p CPUQuota=400% \
    /usr/bin/time -v -o "$log" <command> ) >".tmp/logs/$cmd/${ts}.out" 2>&1 &
echo $! > ".tmp/logs/$cmd/${ts}.pid"
```

Scripts we write ourselves must emit periodic progress to the output log (current step, counts, percent, or heartbeat with a timestamp) so the monitor can tell what they are doing. Flush each line (e.g. Python `print(..., flush=True)` or `PYTHONUNBUFFERED=1`) so progress appears live. The monitor always `tail`s the latest lines of the `.out` log — never reads the full log — to avoid poisoning the session with bulk output.

A consistently too-expensive step is a signal of poor code that needs optimization, not a reason to keep raising the limits — flag it.
```

For richer agent-skill docs, use Matt Pocock's upstream `setup-matt-pocock-skills` skill if installed.

## Verify

- `.gitignore` contains `.env`, `.tmp/`, `.scratch/`, `.worktrees/`, and `.journals/` exactly once.
- `prek.toml` contains the generic hooks, and Python-specific hooks are present only when appropriate for the repo.
- Python repos have a valid `pyproject.toml`; existing project metadata and dependencies were preserved.
- `.opencode/opencode.jsonc` is valid JSONC and includes the schema, plugin, permission, and `mcp` sections.
- Curated skills were installed for the right agent, defaulting to OpenCode unless the user chose another agent.
- `AGENTS.md` exists and contains the `## Repo Workspace Defaults` section, including the `### Resource Limits For Heavy Commands` subsection covering `systemd-run` caps, `/usr/bin/time -v` logging to `.tmp/logs/`, background execution with a monitor sub-agent, flushed progress output from our own scripts, and tail-only log reading.
- Existing `AGENTS.md` content outside `## Repo Workspace Defaults` was preserved.
- No existing file content, config key, array item, or comment was removed without explicit user approval.
