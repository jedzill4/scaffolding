#!/usr/bin/env bash
#
# repo-setup — deterministic bootstrap installer.
#
# Clean adds only. This script NEVER edits, merges, reorders, or overwrites
# existing files. When a target already exists it is left untouched and a notice
# is printed telling you to run the agentic guide for the merge:
#
#   https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/guide.md
#
# Safe to re-run (idempotent): existing targets are skipped, missing ones added.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup/install.sh | bash
#   # or from a checkout:
#   bash setup/install.sh
#
# Environment overrides:
#   AGENT=opencode|claude-code|codex   (default: opencode)
#   RAW_BASE=<url>                      (default: GitHub main)
#   SKIP_SKILLS=1                       (skip npx skills add steps)
#   SKIP_VARLOCK=1                      (skip varlock init)

set -euo pipefail

RAW_BASE="${RAW_BASE:-https://raw.githubusercontent.com/jedzill4/repo-setup/main/setup}"
TEMPLATES="${RAW_BASE}/templates"
AGENT="${AGENT:-opencode}"

# --- logging -----------------------------------------------------------------
c_reset=$'\033[0m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_blue=$'\033[34m'
add()  { printf '%s[add]%s   %s\n'  "$c_green"  "$c_reset" "$1"; }
skip() { printf '%s[skip]%s  %s\n'  "$c_yellow" "$c_reset" "$1"; }
info() { printf '%s[info]%s  %s\n'  "$c_blue"   "$c_reset" "$1"; }
defer() {
  printf '%s[defer]%s %s already exists — left untouched. Run the agentic guide to merge:\n         %s\n' \
    "$c_yellow" "$c_reset" "$1" "$RAW_BASE/guide.md"
}

# --- guards ------------------------------------------------------------------
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
if [ ! -d .git ]; then
  echo "Not a git repository root (no .git/). cd into the repo first." >&2
  exit 1
fi

fetch() { curl -fsSL "$1"; }

# Write a fetched template to a path only if the path does not already exist.
write_if_absent() {
  local url="$1" dest="$2"
  if [ -e "$dest" ]; then
    defer "$dest"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  fetch "$url" > "$dest"
  add "$dest"
}

# --- .gitignore --------------------------------------------------------------
ensure_gitignore() {
  local entries=(".env" ".tmp/" ".scratch/" ".worktrees/" ".journals/")
  [ -e .gitignore ] || { : > .gitignore; add ".gitignore"; }
  local e
  for e in "${entries[@]}"; do
    if grep -qxF "$e" .gitignore 2>/dev/null; then
      skip ".gitignore: $e"
    else
      printf '%s\n' "$e" >> .gitignore
      add ".gitignore: $e"
    fi
  done
}

# --- python detection --------------------------------------------------------
is_python_repo() { [ -f pyproject.toml ] || ls ./*.py >/dev/null 2>&1; }

# --- opencode config ---------------------------------------------------------
ensure_opencode() {
  write_if_absent "$TEMPLATES/opencode-template.jsonc" ".opencode/opencode.jsonc"
}

# --- prek hooks --------------------------------------------------------------
ensure_prek() {
  if [ -e prek.toml ]; then
    defer "prek.toml"
    return 0
  fi
  fetch "$TEMPLATES/prek-generic.toml" > prek.toml
  add "prek.toml (generic hooks)"
  if is_python_repo; then
    { printf '\n'; fetch "$TEMPLATES/prek-python.toml"; } >> prek.toml
    add "prek.toml (python hooks appended)"
    ensure_ast_grep
    write_if_absent "$TEMPLATES/pyproject-template.toml" "pyproject.toml"
  fi
}

# --- ast-grep config ---------------------------------------------------------
ensure_ast_grep() {
  write_if_absent "$TEMPLATES/sgconfig-template.yml" "sgconfig.yml"
  local rule
  for rule in no-dict-call-return no-dict-literal-return no-dict-return-annotation; do
    write_if_absent "$TEMPLATES/ast-grep-rules/${rule}.yml" "ast-grep/rules/${rule}.yml"
  done
}

# --- AGENTS.md ---------------------------------------------------------------
ensure_agents_md() {
  if [ -f AGENTS.md ] && grep -qF "## Repo Workspace Defaults" AGENTS.md; then
    skip "AGENTS.md: ## Repo Workspace Defaults already present"
    return 0
  fi
  if [ ! -f AGENTS.md ]; then
    printf '# Agent Notes\n\n' > AGENTS.md
    add "AGENTS.md (created)"
  fi
  { printf '\n'; fetch "$TEMPLATES/agents-workspace-defaults.md"; } >> AGENTS.md
  add "AGENTS.md: ## Repo Workspace Defaults section"
}

# --- skills ------------------------------------------------------------------
ensure_skills() {
  [ "${SKIP_SKILLS:-0}" = "1" ] && { info "SKIP_SKILLS=1 — skipping skill installs"; return 0; }
  command -v npx >/dev/null 2>&1 || { skip "npx not found — skipping skill installs"; return 0; }
  info "Installing Matt Pocock skills (agent: $AGENT)"
  npx skills add mattpocock/skills --agent "$AGENT" --yes \
    --skill diagnose grill-with-docs triage improve-codebase-architecture tdd \
            to-issues to-prd zoom-out prototype grill-me write-a-skill || skip "matt pocock skills install failed"
  info "Installing recurring local skills: journalist handoff"
  npx skills add jedzill4/repo-setup --agent "$AGENT" --yes --skill journalist handoff || skip "local skills install failed"
  info "Installing dmno-dev/varlock skill"
  npx skills add dmno-dev/varlock --agent "$AGENT" --yes || skip "varlock skill install failed"
}

# --- varlock -----------------------------------------------------------------
ensure_varlock() {
  [ "${SKIP_VARLOCK:-0}" = "1" ] && { info "SKIP_VARLOCK=1 — skipping varlock init"; return 0; }
  if [ -e .env.schema ]; then
    defer ".env.schema (skipping varlock init to avoid rewriting it)"
    return 0
  fi
  if command -v varlock >/dev/null 2>&1; then
    info "Running: varlock init"
    varlock init || skip "varlock init failed"
  elif command -v npx >/dev/null 2>&1; then
    info "Running: npx varlock init --agent"
    npx varlock init --agent || skip "npx varlock init failed"
  else
    skip "varlock/npx not found — install varlock manually (see guide)"
  fi
}

# --- run ---------------------------------------------------------------------
main() {
  info "repo-setup bootstrap (clean adds only) — $(pwd)"
  ensure_gitignore
  ensure_opencode
  ensure_prek
  ensure_agents_md
  ensure_skills
  ensure_varlock
  printf '\n%sDone.%s Existing files (if any) were left untouched; see [defer] notices above and\nrun the agentic guide for merges: %s/guide.md\n' \
    "$c_green" "$c_reset" "$RAW_BASE"
}

main "$@"
