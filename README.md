# repo-setup

Personal repo bootstrap + agent skills for OpenCode-first development.

This repo does two things:

1. **Bootstrap a repo** with my workspace defaults (gitignore, local OpenCode
   config, `AGENTS.md` guidance, optional prek hooks, Varlock secrets). This is a
   one-time-per-repo operation, run as an *agentic install* or a script — not an
   installed skill.
2. **Ship a couple of recurring skills** (`journalist`, `handoff`) that you
   install once and use repeatedly.

Most engineering workflow skills I use come from Matt Pocock's
[`skills`](https://github.com/mattpocock/skills). This repo intentionally does
not vendor those; it only contains my own additions.

## Bootstrap a repo

Run this from the root of the repo you want to set up.

**Existing working repo (recommended): let an agent do it.** The bootstrap needs
judgment — new-vs-existing detection, additive JSONC/`AGENTS.md` merges, Python
detection, and per-item conflict resolution — so point your agent (OpenCode,
Claude Code, Cursor, Amp, …) at the guide and have it follow every step:

> Set up this repo by following the instructions here:
> `https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/guide.md`
> Don't summarize it — follow every step.

**New / empty repo (fast path): run the installer directly.** It does clean adds
only and refuses to touch existing files, deferring any merge to the agent:

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/install.sh | bash
```

The installer is idempotent — safe to re-run. It also installs the recurring
skills below. Override behavior with `AGENT=`, `SKIP_SKILLS=1`, or
`SKIP_VARLOCK=1`.

## Installed skills

These are real skills you install once per agent and use repeatedly. Default
agent target is OpenCode.

Install selected upstream skills from Matt Pocock:

```bash
npx skills add mattpocock/skills --agent opencode --yes --skill diagnose grill-with-docs triage improve-codebase-architecture tdd to-issues to-prd zoom-out prototype grill-me write-a-skill
```

Then install my local skills from this repo:

```bash
npx skills add jedzill4/repo-setup --agent opencode --yes --skill journalist handoff
```

If installing from a checkout, run from this repo:

```bash
npx skills add . --agent opencode --yes --skill journalist handoff --full-depth
```

Use `--agent claude-code` or `--agent codex` instead only when that is the agent
you actually use.

## Upstream skills from Matt Pocock

- `diagnose`, `tdd` — engineering quality workflows.
- `to-prd`, `to-issues`, `triage` — planning and issue workflows.
- `prototype` — throwaway code/UI prototyping.
- `improve-codebase-architecture`, `zoom-out` — architecture and system understanding workflows.
- `grill-me`, `grill-with-docs`, `write-a-skill` — meta/collaboration workflows.

## What's in this repo

- `setup/` — the repo bootstrap. `guide.md` (agentic-install guide),
  `install.sh` (deterministic clean-adds installer), and `templates/`
  (OpenCode config, prek hooks, pyproject, ast-grep rules, AGENTS.md section).
- `skills/productivity/journalist` — local daily session journals under `.journals/`.
- `skills/productivity/handoff` — compact the current session into a temp-dir handoff for another agent.
