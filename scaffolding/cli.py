"""Cyclopts CLI: install, plan, list, check, doctor."""

from __future__ import annotations

import json as _json
from dataclasses import replace
from pathlib import Path

from cyclopts import App

from . import console, prompts
from .checks import run_checks
from .components import AGENT_CHOICES, ALL_CI_PARTS, DEFAULT_CI_PARTS, REGISTRY
from .doctor import probe_tools, repo_state
from .engine import UnknownComponent, build_plan
from .facts import Facts, detect
from .plan import Plan
from .settings import Settings

app = App(
    name="scaffolding",
    help="Deterministic, clean-adds-only repo bootstrap. Existing files are never "
    "edited or overwritten — merges are deferred to the agentic guide.",
)


# --- shared helpers ----------------------------------------------------------
def _settings(yes: bool, agent: str | None, ci: bool | None, no_deps: bool) -> Settings:
    s = Settings()
    if yes:
        s.assume_yes = True
    if agent:
        s.agent = agent
    if ci is True:
        s.with_ci = True
    elif ci is False:
        s.skip_ci = True
    if no_deps:
        s.no_deps = True
    return s


def _split(s: str | None) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


# Dynamic decision map, keyed by component; consumed generically by key.
# ast-grep-ignore: no-dict-return-annotation
def _seed_decisions(
    name: str | None, description: str | None, varlock: bool | None, ci_parts: str | None
) -> dict[str, object]:
    d: dict[str, object] = {}
    if name:
        d["pyproject_name"] = name
    if description:
        d["pyproject_description"] = description
    if varlock is not None:
        d["varlock"] = varlock
    if ci_parts:
        d["ci_parts"] = [p.strip() for p in ci_parts.split(",") if p.strip()]
    return d


def _resolve_decisions(plan: Plan, settings: Settings, decisions: dict) -> None:
    ay = settings.assume_yes
    for dec in plan.decisions:
        if dec.key in decisions:
            continue
        if dec.key == "agent":
            decisions[dec.key] = prompts.select(
                dec.question, AGENT_CHOICES, dec.default, assume_yes=ay
            )
        elif dec.key in ("pyproject_name", "pyproject_description"):
            decisions[dec.key] = prompts.text(dec.question, dec.default, assume_yes=ay)
        elif dec.key == "ci_parts":
            decisions[dec.key] = prompts.checkbox(
                dec.question, ALL_CI_PARTS, DEFAULT_CI_PARTS, assume_yes=ay
            )
        elif dec.key == "varlock":
            decisions[dec.key] = prompts.confirm(dec.question, False, assume_yes=ay)


def _gate_label(comp) -> str:
    fp = Facts("", True, True, False, "public", True, True, True, True, True)
    fn = replace(fp, is_python=False)
    if comp.gate(fn):
        return "always"
    if comp.gate(fp):
        return "python"
    return "never"


# --- install -----------------------------------------------------------------
@app.command
def install(
    components: list[str] | None = None,
    *,
    skip: str | None = None,
    yes: bool = False,
    dry_run: bool = False,
    agent: str | None = None,
    ci: bool | None = None,
    ci_parts: str | None = None,
    name: str | None = None,
    description: str | None = None,
    varlock: bool | None = None,
    no_deps: bool = False,
):
    """Apply clean-adds for the selected components (or all default-on)."""
    root = Path.cwd()
    settings = _settings(yes, agent, ci, no_deps)
    facts = detect(root)

    if not facts.is_git_repo and not dry_run:
        console.err_console.print(
            "[red]Not a git repository root (no .git/). cd into the repo first.[/red]"
        )
        raise SystemExit(1)

    interactive = prompts.is_interactive(settings.assume_yes)

    # Tier-2 CI opt-in (full interactive install only).
    ci_optin = interactive and not components and not settings.with_ci and not settings.skip_ci
    if ci_optin and prompts.confirm(
        "Add GitHub Actions workflows (tests, security, docker)?", False, assume_yes=False
    ):
        settings.with_ci = True

    decisions = _seed_decisions(name, description, varlock, ci_parts)

    try:
        plan = build_plan(
            root,
            facts,
            settings,
            requested=components or [],
            skip=_split(skip),
            decisions=decisions,
            interactive=interactive,
        )
    except UnknownComponent as exc:
        console.err_console.print(f"[red]Unknown component: {exc}[/red]  (try: scaffolding list)")
        raise SystemExit(2) from exc

    if interactive:
        _resolve_decisions(plan, settings, decisions)
        plan = build_plan(
            root,
            facts,
            settings,
            requested=components or [],
            skip=_split(skip),
            decisions=decisions,
            interactive=interactive,
        )

    if dry_run:
        console.render_plan_table(plan, title="Plan (dry-run — nothing written)")
        return

    from .engine import apply

    code = apply(plan, root)
    console.console.print(
        f"\n[green]Done.[/green] Existing files left untouched; see \\[defer] notices and "
        f"merge via the guide: {settings.raw_base}/guide.md"
    )
    if code:
        raise SystemExit(code)


# --- plan --------------------------------------------------------------------
@app.command(name="plan")
def plan_cmd(
    components: list[str] | None = None,
    *,
    skip: str | None = None,
    json: bool = False,
    agent: str | None = None,
    ci: bool | None = None,
    no_deps: bool = False,
    ci_parts: str | None = None,
    name: str | None = None,
    description: str | None = None,
    varlock: bool | None = None,
):
    """Build the plan and print it (machine-readable with --json). Writes nothing."""
    root = Path.cwd()
    settings = _settings(False, agent, ci, no_deps)
    facts = detect(root)
    decisions = _seed_decisions(name, description, varlock, ci_parts)
    try:
        plan = build_plan(
            root,
            facts,
            settings,
            requested=components or [],
            skip=_split(skip),
            decisions=decisions,
            interactive=False,
        )
    except UnknownComponent as exc:
        console.err_console.print(f"[red]Unknown component: {exc}[/red]")
        raise SystemExit(2) from exc

    if json:
        print(_json.dumps(plan.to_json_obj(), indent=2))
    else:
        console.render_plan_table(plan, title="Plan")


# --- list --------------------------------------------------------------------
@app.command(name="list")
def list_cmd():
    """List available components, their gate, default, and what they add."""
    from rich.table import Table

    table = Table(title="Components")
    table.add_column("component", no_wrap=True)
    table.add_column("default", no_wrap=True)
    table.add_column("gate", no_wrap=True)
    table.add_column("tier", no_wrap=True)
    table.add_column("adds")
    for comp in REGISTRY:
        default = "on" if comp.default_on else "opt-in"
        table.add_row(comp.name, default, _gate_label(comp), str(comp.tier), comp.summary)
    console.console.print(table)


# --- check -------------------------------------------------------------------
@app.command
def check():
    """Verify bootstrap completeness. Exits nonzero on any failure."""
    from rich.table import Table

    results = run_checks(Path.cwd())
    table = Table(title="scaffolding check")
    table.add_column("status", no_wrap=True)
    table.add_column("check", no_wrap=True)
    table.add_column("detail")
    failed = 0
    for r in results:
        if r.ok:
            table.add_row("[green]pass[/green]", r.name, r.detail)
        else:
            failed += 1
            table.add_row("[red]FAIL[/red]", r.name, r.detail)
    console.console.print(table)
    if failed:
        console.console.print(f"[red]{failed} check(s) failed.[/red]")
        raise SystemExit(1)
    console.console.print("[green]All checks passed.[/green]")


# --- doctor ------------------------------------------------------------------
@app.command
def doctor():
    """Diagnose the environment (tools + repo state) with suggested fixes."""
    from rich.table import Table

    tools = Table(title="Tools")
    tools.add_column("tool", no_wrap=True)
    tools.add_column("status", no_wrap=True)
    tools.add_column("version")
    tools.add_column("fix")
    for p in probe_tools():
        status = "[green]ok[/green]" if p.ok else "[red]missing[/red]"
        tools.add_row(p.name, status, p.version, p.fix)
    console.console.print(tools)

    state = Table(title="Repo")
    state.add_column("fact", no_wrap=True)
    state.add_column("value")
    for k, v in repo_state(Path.cwd()).items():
        state.add_row(k, str(v))
    console.console.print(state)


if __name__ == "__main__":
    app()
