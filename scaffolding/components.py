"""Component registry: each former ensure_* step as a selectable component.

Every component exposes ``plan(ctx) -> list[Op]`` that inspects the filesystem
and facts and returns ops WITHOUT side effects (apply executes them). Plan may
register Tier-2/3 ``Decision``s via ``ctx.add_decision``.
"""

from __future__ import annotations

import contextlib
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from scaffolding.plan import Decision, Decisions, Disposition, Op
from scaffolding.templates_registry import template_text

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from scaffolding.facts import Facts
    from scaffolding.settings import Settings

GITIGNORE_ENTRIES = [".env", "!.env.schema", ".tmp/", ".scratch/", ".worktrees/", ".journals/"]
AGENTS_MARKER = "## Repo Workspace Defaults"
# Marker-gated section the `standards` component owns in AGENTS.md (sibling to AGENTS_MARKER).
STANDARDS_MARKER = "## Engineering Standards"
# Per-CES detail files under .agents/rules/ shipped by the standards component. One file per
# standard (a CES may ship several ast-grep/prek slugs but documents them in one detail file).
STANDARDS_RULE_DETAILS = [
    "no-dict",
    "file-size-guard",
    "log-get-logger",
    "log-no-print",
    "core-logger",
    "api-schemas-extra-forbid",
    "settings-module",
    "cli-typed-framework",
    "arch-database-package",
    "no-utils",
    "repo-shape",
    "agents-conventional-commits",
    "import-linter",
    "api-boundary-layout",
    "arch-vocabulary",
    "spaghetti-mixed-orchestration",
    "general-respect-local-repo",
    "py-legacy-lint-stack",
    "test-in-memory-adapters",
    "test-through-interface",
    "test-coverage-gap",
]
# Canonical drop-in / comparison code shipped under snippets/ (may be nested, e.g. core/logger.py).
STANDARDS_SNIPPETS = [
    "no-dict-boundary.py",
    "core/logger.py",
    "api-schemas.py",
    "settings.py",
    "tests/in_memory_repository.py",
]
ASTGREP_RULES = [
    "no-dict-call-return",
    "no-dict-literal-return",
    "no-dict-return-annotation",
    "no-dict-alias",
    "log-get-logger",
    "log-no-print",
    "api-schemas-extra-forbid",
    "settings-module",
    "cli-typed-framework",
    "arch-database-package",
]
MATTPOCOCK_SKILLS = [
    "setup-matt-pocock-skills",
    "diagnose",
    "grill-with-docs",
    "triage",
    "improve-codebase-architecture",
    "tdd",
    "to-issues",
    "to-prd",
    "zoom-out",
    "prototype",
    "grill-me",
    "write-a-skill",
]
DEFAULT_CI_PARTS = ["tests", "security", "docker"]
# "opencode" is opt-in only (off by default): it needs repo secrets and the
# OpenCode GitHub App installed, so it is never added unless explicitly chosen.
ALL_CI_PARTS = ["tests", "security", "docker", "publish", "opencode"]
AGENT_CHOICES = ["opencode", "claude-code", "codex"]


@dataclass
class Context:
    root: Path
    facts: Facts
    settings: Settings
    decisions: Decisions
    interactive: bool
    _decisions: list[Decision] = field(default_factory=list)

    @property
    def guide_url(self) -> str:
        return f"{self.settings.raw_base}/guide.md"

    def add_decision(self, d: Decision) -> None:
        if all(existing.key != d.key for existing in self._decisions):
            self._decisions.append(d)


@dataclass
class Component:
    name: str
    summary: str
    tier: int
    default_on: bool
    gate: Callable[[Facts], bool]
    plan: Callable[[Context], list[Op]]
    deps: Callable[[Facts], list[str]] = field(default=lambda f: [])


# --- helpers -----------------------------------------------------------------
def _norm_name(s: str) -> str:
    return s.strip().lower().replace(" ", "-").replace("_", "-")


def infer_project_name(root: Path) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            tail = out.stdout.strip().rstrip("/").split("/")[-1].removesuffix(".git")
            if tail:
                return _norm_name(tail)
    return _norm_name(root.name)


def _write_if_absent(component: str, dest: Path, content: str, label: str, guide_url: str) -> Op:
    if dest.exists():
        return Op(
            component,
            "noop",
            label,
            Disposition.DEFER,
            detail=f"already exists — left untouched. Merge via guide: {guide_url}",
        )
    return Op(component, "write", label, Disposition.ADD, path=str(dest), content=content)


# --- gates -------------------------------------------------------------------
def _always(_f: Facts) -> bool:
    return True


def _python(f: Facts) -> bool:
    return f.is_python


# --- component plans ---------------------------------------------------------
def plan_gitignore(ctx: Context) -> list[Op]:
    dest = ctx.root / ".gitignore"
    if not dest.exists():
        content = "\n".join(GITIGNORE_ENTRIES) + "\n"
        return [
            Op(
                "gitignore",
                "write",
                ".gitignore",
                Disposition.ADD,
                path=str(dest),
                content=content,
                detail="create with workspace entries",
            )
        ]
    present = {ln.rstrip() for ln in dest.read_text(encoding="utf-8").splitlines()}
    missing = [e for e in GITIGNORE_ENTRIES if e not in present]
    if not missing:
        return [
            Op("gitignore", "noop", ".gitignore", Disposition.SKIP, detail="all entries present")
        ]
    return [
        Op(
            "gitignore",
            "append",
            ".gitignore",
            Disposition.ADD,
            path=str(dest),
            content="\n".join(missing) + "\n",
            detail="add: " + ", ".join(missing),
        )
    ]


def plan_opencode(ctx: Context) -> list[Op]:
    dest = ctx.root / "opencode.jsonc"
    return [
        _write_if_absent(
            "opencode",
            dest,
            template_text("opencode-template.jsonc"),
            "opencode.jsonc",
            ctx.guide_url,
        )
    ]


def plan_prek(ctx: Context) -> list[Op]:
    dest = ctx.root / "prek.toml"
    if dest.exists():
        return [
            Op(
                "prek",
                "noop",
                "prek.toml",
                Disposition.DEFER,
                detail=f"already exists — merge via guide: {ctx.guide_url}",
            )
        ]
    content = template_text("prek-generic.toml")
    detail = "generic hooks"
    if ctx.facts.is_python:
        content += "\n" + template_text("prek-python.toml")
        detail = "generic + python hooks"
    return [
        Op(
            "prek",
            "write",
            "prek.toml",
            Disposition.ADD,
            path=str(dest),
            content=content,
            detail=detail,
        )
    ]


def plan_astgrep(ctx: Context) -> list[Op]:
    ops = [
        _write_if_absent(
            "ast-grep",
            ctx.root / "sgconfig.yml",
            template_text("sgconfig-template.yml"),
            "sgconfig.yml",
            ctx.guide_url,
        )
    ]
    for rule in ASTGREP_RULES:
        dest = ctx.root / "ast-grep" / "rules" / f"{rule}.yml"
        ops.append(
            _write_if_absent(
                "ast-grep",
                dest,
                template_text(f"ast-grep-rules/{rule}.yml"),
                f"ast-grep/rules/{rule}.yml",
                ctx.guide_url,
            )
        )
    return ops


def plan_pyproject(ctx: Context) -> list[Op]:
    dest = ctx.root / "pyproject.toml"
    if dest.exists():
        return [
            Op(
                "pyproject",
                "noop",
                "pyproject.toml",
                Disposition.DEFER,
                detail=f"already exists — merge via guide: {ctx.guide_url}",
            )
        ]
    name = ctx.decisions.pyproject_name or infer_project_name(ctx.root)
    desc = ctx.decisions.pyproject_description or f"{name} project"
    ctx.add_decision(Decision(2, "pyproject_name", "Project name?", name))
    ctx.add_decision(Decision(2, "pyproject_description", "Project description?", desc))
    content = (
        template_text("pyproject-template.toml")
        .replace('name = "replace-me"', f'name = "{name}"')
        .replace('description = "Replace me"', f'description = "{desc}"')
    )
    return [
        Op(
            "pyproject",
            "write",
            "pyproject.toml",
            Disposition.ADD,
            path=str(dest),
            content=content,
            detail=f"name={name}",
        )
    ]


def plan_ci(ctx: Context) -> list[Op]:
    parts = ctx.decisions.ci_parts or DEFAULT_CI_PARTS
    ctx.add_decision(
        Decision(
            2,
            "ci_parts",
            "Which CI parts? (tests,security,docker,publish,opencode)",
            ",".join(DEFAULT_CI_PARTS),
        )
    )
    # CES-75: Conventional Commits PR check ships whenever CI is set up, independent of parts
    # (it mirrors the always-on commit-msg prek hook).
    ops: list[Op] = [
        _write_if_absent(
            "ci",
            ctx.root / ".github/workflows/conventional-commits.yml",
            template_text("github/workflows/conventional-commits.yml"),
            ".github/workflows/conventional-commits.yml",
            ctx.guide_url,
        )
    ]
    if "security" in parts:
        ops.append(
            _write_if_absent(
                "ci",
                ctx.root / ".github/workflows/zizmor.yml",
                template_text("github/workflows/zizmor.yml"),
                ".github/workflows/zizmor.yml",
                ctx.guide_url,
            )
        )
        ops.append(
            _write_if_absent(
                "ci",
                ctx.root / ".github/zizmor.yml",
                template_text("github/zizmor.yml"),
                ".github/zizmor.yml",
                ctx.guide_url,
            )
        )
    if "tests" in parts and ctx.facts.is_python:
        ops.append(
            _write_if_absent(
                "ci",
                ctx.root / ".github/workflows/tests.yml",
                template_text("github/workflows/tests.yml"),
                ".github/workflows/tests.yml",
                ctx.guide_url,
            )
        )
        ops.append(
            _write_if_absent(
                "ci",
                ctx.root / ".github/workflows/pip-audit.yml",
                template_text("github/workflows/pip-audit.yml"),
                ".github/workflows/pip-audit.yml",
                ctx.guide_url,
            )
        )
        ops.append(
            _write_if_absent(
                "ci",
                ctx.root / ".github/dependabot.yml",
                template_text("github/dependabot.yml"),
                ".github/dependabot.yml",
                ctx.guide_url,
            )
        )
    if "docker" in parts and ctx.facts.has_dockerfile:
        if ctx.facts.visibility in ("private", "internal"):
            ops.append(
                Op(
                    "ci",
                    "noop",
                    ".github/workflows/docker.yml",
                    Disposition.SKIP,
                    detail="repo non-public — docker.yml pushes to GHCR (bills private "
                    "packages past the free tier). Skipped; add manually if intended.",
                )
            )
        else:
            ops.append(
                _write_if_absent(
                    "ci",
                    ctx.root / ".github/workflows/docker.yml",
                    template_text("github/workflows/docker.yml"),
                    ".github/workflows/docker.yml",
                    ctx.guide_url,
                )
            )
    if "publish" in parts:
        ops += [
            _write_if_absent(
                "ci",
                ctx.root / f".github/workflows/{wf}",
                template_text(f"github/workflows/{wf}"),
                f".github/workflows/{wf}",
                ctx.guide_url,
            )
            for wf in ("release.yml", "pypi.yml")
        ]
    if "opencode" in parts:
        ops += [
            _write_if_absent(
                "ci",
                ctx.root / f".github/workflows/{wf}",
                template_text(f"github/workflows/{wf}"),
                f".github/workflows/{wf}",
                ctx.guide_url,
            )
            for wf in ("opencode.yml", "proposal-update.yml")
        ]
    if not ops:
        ops.append(Op("ci", "noop", "ci", Disposition.SKIP, detail="no applicable CI parts"))
    return ops


def plan_agents(ctx: Context) -> list[Op]:
    dest = ctx.root / "AGENTS.md"
    section = template_text("agents-workspace-defaults.md")
    if dest.exists():
        if AGENTS_MARKER in dest.read_text(encoding="utf-8"):
            return [
                Op(
                    "agents",
                    "noop",
                    "AGENTS.md",
                    Disposition.SKIP,
                    detail=f"{AGENTS_MARKER} already present",
                )
            ]
        return [
            Op(
                "agents",
                "append",
                "AGENTS.md",
                Disposition.ADD,
                path=str(dest),
                content="\n" + section,
                detail="append workspace-defaults section",
            )
        ]
    return [
        Op(
            "agents",
            "write",
            "AGENTS.md",
            Disposition.ADD,
            path=str(dest),
            content="# Agent Notes\n\n" + section,
            detail="create with section",
        )
    ]


def _standards_index_op(ctx: Context) -> Op:
    """Append the marker-gated ## Engineering Standards index to AGENTS.md (idempotent)."""
    dest = ctx.root / "AGENTS.md"
    section = template_text("standards-index.md")
    if dest.exists() and STANDARDS_MARKER in dest.read_text(encoding="utf-8"):
        return Op(
            "standards",
            "noop",
            "AGENTS.md",
            Disposition.SKIP,
            detail=f"{STANDARDS_MARKER} already present",
        )
    # Always append (never create/overwrite): the `agents` dep creates the AGENTS.md base, and
    # _apply_append tolerates a missing file, so this can never clobber an existing AGENTS.md.
    return Op(
        "standards",
        "append",
        "AGENTS.md",
        Disposition.ADD,
        path=str(dest),
        content="\n" + section,
        detail="append Engineering Standards index",
    )


def plan_standards(ctx: Context) -> list[Op]:
    ops = [_standards_index_op(ctx)]
    ops += [
        _write_if_absent(
            "standards",
            ctx.root / ".agents" / "rules" / f"{slug}.md",
            template_text(f"agents-rules/{slug}.md"),
            f".agents/rules/{slug}.md",
            ctx.guide_url,
        )
        for slug in STANDARDS_RULE_DETAILS
    ]
    ops += [
        _write_if_absent(
            "standards",
            ctx.root / "snippets" / snippet,
            template_text(f"snippets/{snippet}"),
            f"snippets/{snippet}",
            ctx.guide_url,
        )
        for snippet in STANDARDS_SNIPPETS
    ]
    return ops


def plan_skills(ctx: Context) -> list[Op]:
    if ctx.settings.skip_skills:
        return [Op("skills", "noop", "skills", Disposition.SKIP, detail="SKIP_SKILLS set")]
    if not ctx.facts.has_npx:
        return [Op("skills", "noop", "skills", Disposition.SKIP, detail="npx not found")]
    agent = ctx.decisions.agent or ctx.settings.agent
    ctx.add_decision(
        Decision(2, "agent", "Which agent target? (opencode/claude-code/codex)", agent)
    )
    cmds = [
        [
            "npx",
            "skills",
            "add",
            "mattpocock/skills",
            "--agent",
            agent,
            "--yes",
            "--skill",
            *MATTPOCOCK_SKILLS,
        ],
        [
            "npx",
            "skills",
            "add",
            "jedzill4/scaffolding",
            "--agent",
            agent,
            "--yes",
            "--skill",
            "journalist",
            "handoff",
        ],
        ["npx", "skills", "add", "dmno-dev/varlock", "--agent", agent, "--yes"],
    ]
    labels = [
        f"matt pocock skills (agent: {agent})",
        f"local skills: journalist handoff (agent: {agent})",
        f"dmno-dev/varlock skill (agent: {agent})",
    ]
    return [
        Op("skills", "run", labels[i], Disposition.RUN, cmd=cmds[i], optional=True)
        for i in range(len(cmds))
    ]


def plan_varlock(ctx: Context) -> list[Op]:
    if ctx.settings.skip_varlock:
        return [Op("varlock", "noop", "varlock", Disposition.SKIP, detail="SKIP_VARLOCK set")]
    if (ctx.root / ".env.schema").exists():
        return [
            Op(
                "varlock",
                "noop",
                ".env.schema",
                Disposition.DEFER,
                detail="exists — skipping varlock init to avoid rewriting it",
            )
        ]
    if (ctx.root / ".env.example").exists():
        ctx.add_decision(
            Decision(
                3, "varlock", "Run varlock init? .env.example exists and may be rewritten", "no"
            )
        )
        if not ctx.decisions.varlock:
            return [
                Op(
                    "varlock",
                    "noop",
                    "varlock init",
                    Disposition.SKIP,
                    detail=".env.example exists — pass --varlock to run init",
                )
            ]
    if ctx.facts.has_varlock:
        cmd = ["varlock", "init"]
    elif ctx.facts.has_npx:
        cmd = ["npx", "varlock", "init", "--agent"]
    else:
        return [Op("varlock", "noop", "varlock", Disposition.SKIP, detail="varlock/npx not found")]
    return [Op("varlock", "run", "varlock init", Disposition.RUN, cmd=cmd, optional=True)]


# --- registry ----------------------------------------------------------------
REGISTRY: list[Component] = [
    Component("gitignore", "Workspace .gitignore entries", 1, True, _always, plan_gitignore),
    Component("opencode", "Repo-local opencode.jsonc", 1, True, _always, plan_opencode),
    Component(
        "prek",
        "prek.toml hooks (generic + python)",
        1,
        True,
        _always,
        plan_prek,
        deps=lambda f: ["ast-grep"] if f.is_python else [],
    ),
    Component("ast-grep", "sgconfig.yml + starter rules", 1, True, _python, plan_astgrep),
    Component(
        "pyproject", "pyproject.toml (guided name/description)", 2, True, _python, plan_pyproject
    ),
    Component("ci", "GitHub Actions workflows + dependabot", 2, False, _always, plan_ci),
    Component("agents", "AGENTS.md workspace-defaults section", 1, True, _always, plan_agents),
    Component(
        "standards",
        "Engineering Standards index + .agents/rules detail + snippets",
        1,
        True,
        _python,
        plan_standards,
        deps=lambda f: ["agents"],
    ),
    Component("skills", "Install curated agent skills via npx", 2, True, _always, plan_skills),
    Component("varlock", "Varlock secret schema init", 3, True, _always, plan_varlock),
]

BY_NAME = {c.name: c for c in REGISTRY}


def lookup(name: str) -> Component | None:
    return BY_NAME.get(name)
