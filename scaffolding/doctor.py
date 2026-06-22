"""`doctor` — environment/tool diagnosis with suggested fixes."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .facts import detect


@dataclass
class Probe:
    name: str
    ok: bool
    version: str
    fix: str


_TOOLS = {
    "git": "install git (https://git-scm.com)",
    "curl": "install curl",
    "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "npx": "install Node.js 22+ (https://nodejs.org)",
    "gh": "install GitHub CLI (https://cli.github.com)",
    "varlock": "npx varlock init  OR  brew install dmno-dev/tap/varlock",
}


def _version(cmd: str) -> str:
    for flag in ("--version", "version", "-V"):
        with contextlib.suppress(OSError, subprocess.SubprocessError, IndexError):
            out = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=8)
            if out.returncode == 0:
                return (out.stdout or out.stderr).strip().splitlines()[0]
    return ""


def probe_tools() -> list[Probe]:
    probes: list[Probe] = []
    for tool, fix in _TOOLS.items():
        present = shutil.which(tool) is not None
        probes.append(
            Probe(tool, present, _version(tool) if present else "", "" if present else fix)
        )
    return probes


# JSON-serialization boundary: dict is the JSON representation here.
# ast-grep-ignore: no-dict-return-annotation
def repo_state(root: Path | None = None) -> dict[str, object]:
    facts = detect(root)
    state: dict[str, object] = {
        "git repo root": facts.is_git_repo,
        "python repo": facts.is_python,
        "Dockerfile": facts.has_dockerfile,
        "visibility": facts.visibility,
    }
    return state
