"""Tier-0 facts: deterministic repo/environment detection (never asked)."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Facts:
    cwd: str
    is_git_repo: bool
    is_python: bool
    has_dockerfile: bool
    visibility: str  # public | private | internal | unknown
    has_npx: bool
    has_gh: bool
    has_varlock: bool
    has_uv: bool
    has_curl: bool

    # JSON-serialization boundary: dict is the JSON representation here.
    # ast-grep-ignore: no-dict-return-annotation
    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def repo_visibility() -> str:
    if not _has("gh"):
        return "unknown"
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0:
            return out.stdout.strip().lower() or "unknown"
    return "unknown"


def is_python_repo(root: Path) -> bool:
    if (root / "pyproject.toml").exists():
        return True
    return any(root.glob("*.py"))


def detect(root: Path | None = None, *, probe_visibility: bool = True) -> Facts:
    root = root or Path.cwd()
    return Facts(
        cwd=str(root),
        is_git_repo=(root / ".git").is_dir(),
        is_python=is_python_repo(root),
        has_dockerfile=(root / "Dockerfile").exists(),
        visibility=repo_visibility() if probe_visibility else "unknown",
        has_npx=_has("npx"),
        has_gh=_has("gh"),
        has_varlock=_has("varlock"),
        has_uv=_has("uv"),
        has_curl=_has("curl"),
    )
