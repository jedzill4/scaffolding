"""Plan / Op data model and JSON serialization (the Model A backbone)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Disposition(StrEnum):
    ADD = "add"
    SKIP = "skip"
    DEFER = "defer"
    RUN = "run"
    WARN = "warn"


@dataclass
class Op:
    """One planned operation. Plan computes everything; apply just executes."""

    component: str
    kind: str  # write | append | run | noop
    target: str
    disposition: Disposition
    detail: str = ""
    path: str | None = None
    content: str | None = None
    cmd: list[str] | None = None
    optional: bool = False

    # JSON-serialization boundary: dict is the JSON representation here.
    # ast-grep-ignore: no-dict-return-annotation
    def to_dict(self) -> dict[str, object]:
        obj: dict[str, object] = {
            "component": self.component,
            "kind": self.kind,
            "target": self.target,
            "disposition": self.disposition.value,
            "detail": self.detail,
        }
        return obj


@dataclass
class Decision:
    """A Tier-2/3 choice that must be made by the user (even agentic)."""

    tier: int
    key: str
    question: str
    default: str

    # JSON-serialization boundary: dict is the JSON representation here.
    # ast-grep-ignore: no-dict-return-annotation
    def to_dict(self) -> dict[str, object]:
        obj: dict[str, object] = {
            "tier": self.tier,
            "key": self.key,
            "question": self.question,
            "default": self.default,
        }
        return obj


@dataclass
class Plan:
    facts: dict
    ops: list[Op] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def by(self, disp: Disposition) -> list[Op]:
        return [o for o in self.ops if o.disposition == disp]

    @property
    def deferred_merges(self) -> list[str]:
        return [o.target for o in self.by(Disposition.DEFER)]

    # JSON-serialization boundary: dict is the JSON representation here.
    # ast-grep-ignore: no-dict-return-annotation
    def to_json_obj(self) -> dict[str, object]:
        obj: dict[str, object] = {
            "facts": self.facts,
            "clean_adds": [o.to_dict() for o in self.by(Disposition.ADD)],
            "runs": [o.to_dict() for o in self.by(Disposition.RUN)],
            "skips": [o.to_dict() for o in self.by(Disposition.SKIP)],
            "defers": [o.to_dict() for o in self.by(Disposition.DEFER)],
            "warnings": [o.to_dict() for o in self.by(Disposition.WARN)],
            "decisions_needed": [d.to_dict() for d in self.decisions],
            "deferred_merges": self.deferred_merges,
            "notices": self.notices,
        }
        return obj
