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
#   WITH_CI=1 | SKIP_CI=1              (force-add / skip GitHub Actions
#                                       workflows without prompting)
#   ASSUME_YES=1                        (answer all prompts with their default)

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

# --- prompts -----------------------------------------------------------------
# ask_yes_no "Question?" <default:y|n> — returns 0 for yes, 1 for no.
# Reads from the controlling terminal so it works under `curl | bash`. When
# there is no terminal (or ASSUME_YES=1), it returns the default without asking,
# keeping non-interactive runs deterministic.
ask_yes_no() {
  local prompt="$1" default="${2:-n}" reply hint
  [ "$default" = y ] && hint="Y/n" || hint="y/N"
  # Interactive only when stdout is a terminal and /dev/tty can be opened.
  if [ "${ASSUME_YES:-0}" = "1" ] || [ ! -t 1 ] || ! { : < /dev/tty; } 2>/dev/null; then
    reply="$default"
  else
    printf '%s[ask]%s   %s [%s] ' "$c_blue" "$c_reset" "$prompt" "$hint" > /dev/tty
    read -r reply < /dev/tty || reply="$default"
    reply="${reply:-$default}"
  fi
  case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
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
  # .env.schema is the committed source of truth — keep it tracked even if a
  # broader .env* pattern is added later.
  local entries=(".env" "!.env.schema" ".tmp/" ".scratch/" ".worktrees/" ".journals/")
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

# --- repo visibility ---------------------------------------------------------
# Echoes "public", "private", "internal", or "" (unknown) using the gh CLI.
repo_visibility() {
  command -v gh >/dev/null 2>&1 || return 0
  gh repo view --json visibility -q '.visibility' 2>/dev/null | tr '[:upper:]' '[:lower:]'
}

# --- opencode config ---------------------------------------------------------
ensure_opencode() {
  write_if_absent "$TEMPLATES/opencode-template.jsonc" "opencode.jsonc"
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

# --- github actions CI -------------------------------------------------------
# Opt-in. The user is asked before any workflow is written (default: no), so
# repos that don't want CI stay clean. Overrides: WITH_CI=1 adds without asking,
# SKIP_CI=1 skips without asking. Within the suite, publish-only workflows stay
# opt-in and are documented in the guide instead of being scaffolded:
#   - release.yml / pypi.yml: PyPI publishing only makes sense for a *public*
#     Python package, and needs a tagged release flow + Trusted Publishing.
#   - docker.yml: pushes to GHCR. GHCR is free for *public* packages; private
#     packages bill storage/bandwidth past the free tier — so we warn first.
ensure_ci() {
  if [ "${SKIP_CI:-0}" = "1" ]; then
    info "SKIP_CI=1 — skipping GitHub Actions workflows"
    return 0
  fi
  if [ "${WITH_CI:-0}" != "1" ]; then
    if ! ask_yes_no "Add GitHub Actions workflows (tests, security scans, dependabot)?" n; then
      info "Skipping GitHub Actions workflows (re-run with WITH_CI=1 to add them)"
      return 0
    fi
  fi

  # zizmor: GitHub Actions workflow/action static analysis (any repo).
  write_if_absent "$TEMPLATES/github/workflows/zizmor.yml" ".github/workflows/zizmor.yml"

  if is_python_repo; then
    # Test/lint workflow + dependency vuln scan + dependabot (uv-based repos).
    write_if_absent "$TEMPLATES/github/workflows/tests.yml" ".github/workflows/tests.yml"
    write_if_absent "$TEMPLATES/github/workflows/pip-audit.yml" ".github/workflows/pip-audit.yml"
    write_if_absent "$TEMPLATES/github/dependabot.yml" ".github/dependabot.yml"
  fi

  # docker.yml only when the repo actually ships a Dockerfile. Warn about GHCR
  # billing for non-public repos before adding it.
  if [ -f Dockerfile ]; then
    case "$(repo_visibility)" in
      private|internal)
        skip "Dockerfile found, but repo is non-public — docker.yml pushes to GHCR, which bills storage/bandwidth for private packages past the free tier. Left untouched; add it manually (or publish the package) if that's intended."
        ;;
      *)
        write_if_absent "$TEMPLATES/github/workflows/docker.yml" ".github/workflows/docker.yml"
        ;;
    esac
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
  ensure_ci
  ensure_agents_md
  ensure_skills
  ensure_varlock
  printf '\n%sDone.%s Existing files (if any) were left untouched; see [defer] notices above and\nrun the agentic guide for merges: %s/guide.md\n' \
    "$c_green" "$c_reset" "$RAW_BASE"
}

main "$@"
