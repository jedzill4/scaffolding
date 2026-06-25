"""Textual TUI to review scaffolding rule-proposal issues.

List view: sortable (priority / activity / number, or click a column header) and
filterable via a multi-select checklist over type / state / area plus free text.
Detail view: read the proposal body + comments and approve / decline / had-comments / comment.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import webbrowser
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    SelectionList,
    TextArea,
)

from review import gh
from review.gh import PRIORITY_RANK, Issue, IssueDetail

# Canonical display order for the checklist; any values seen on issues but not
# listed here are appended alphabetically so new label vocab still shows up.
STATE_ORDER = ["proposal", "had-comments", "approved", "declined"]
TYPE_ORDER = ["proposal", "bug", "feature", "build", "question"]

# Sort modes the `S` key cycles through. Column-header clicks can additionally
# select any of the per-column modes in COLUMN_SORT (see _sort_key).
SORT_CYCLE = ["pri", "activity", "number"]
SORT_LABEL = {
    "pri": "priority",
    "activity": "activity",
    "number": "#",
    "comments": "comments",
    "state": "state",
    "area": "area",
    "enforcer": "enforcer",
    "title": "title",
}
# Modes that read most-naturally newest/highest-first when first selected.
SORT_DEFAULT_DESC = {"activity"}

# Cell colours (Rich style strings).
STATE_STYLE = {
    "proposal": "cyan",
    "had-comments": "yellow",
    "approved": "green",
    "declined": "red",
}
PRIORITY_STYLE = {"high": "bold red", "medium": "yellow", "low": "dim green"}
# Stable per-area palette: same area always gets the same colour.
AREA_PALETTE = ["magenta", "blue", "cyan", "green", "bright_magenta", "bright_blue", "bright_cyan"]

# Activity older than this many days renders greyed-out (and as a bare date).
OLD_ACTIVITY_DAYS = 14


def _area_style(area: str) -> str:
    if not area:
        return ""
    return AREA_PALETTE[zlib.crc32(area.encode()) % len(AREA_PALETTE)]


def _styled(value: str, style: str) -> Text:
    return Text(value, style=style)


def _relative_activity(iso: str) -> Text:
    """Render an ISO timestamp as a relative 'time ago' label.

    '5 min ago' / '3h ago' / '2d ago', or a bare date once it's older than
    OLD_ACTIVITY_DAYS. Old activity is greyed out.
    """
    if not iso:
        return Text("")
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return Text(iso[:10], style="dim")
    delta = datetime.now(UTC) - when
    secs = delta.total_seconds()
    days = delta.days
    if days >= OLD_ACTIVITY_DAYS:
        return Text(when.date().isoformat(), style="dim")
    if secs < 60:
        label = "just now"
    elif secs < 3600:
        label = f"{int(secs // 60)} min ago"
    elif secs < 86400:
        label = f"{int(secs // 3600)}h ago"
    else:
        label = f"{days}d ago"
    return Text(label)


def _refresh_seconds() -> float:
    """Auto-refresh poll interval in seconds (0 disables). Override via env."""
    try:
        return max(0.0, float(os.environ.get("REVIEW_REFRESH_SECONDS", "30")))
    except ValueError:
        return 30.0


REFRESH_SECONDS = _refresh_seconds()

# Turn GitHub-style `#123` issue references into clickable links (href `issue:123`).
# Skips markdown headers (`#` + space) and `#abc` hex/anchor tokens (digits only).
ISSUE_REF = re.compile(r"(?<![\w#/])#(\d{1,6})\b")


class CommentModal(ModalScreen[str | None]):
    """Prompt for a comment body."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="comment-box"):
            yield TextArea(id="comment-text")
            yield Button("Submit (ctrl+s)", id="submit", variant="primary")

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    def key_ctrl_s(self) -> None:
        self.dismiss(self.query_one(TextArea).text.strip() or None)

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(self.query_one(TextArea).text.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FilterState:
    """Active filters: multi-select sets per axis (empty = no constraint) + free text."""

    def __init__(self) -> None:
        self.types: set[str] = {"proposal"}  # default to proposals; clear (x) to see all
        self.states: set[str] = set()
        self.areas: set[str] = set()
        self.query: str = ""

    def is_empty(self) -> bool:
        return not (self.types or self.states or self.areas or self.query)

    def clear(self) -> None:
        self.types, self.states, self.areas, self.query = set(), set(), set(), ""

    def matches(self, i: Issue) -> bool:
        if self.types and i.type not in self.types:
            return False
        if self.states and i.state not in self.states:
            return False
        if self.areas and i.area not in self.areas:
            return False
        if self.query:
            q = self.query.lower()
            if q not in i.title.lower() and not any(q in lab.lower() for lab in i.labels):
                return False
        return True

    def summary(self) -> str:
        bits = []
        for name, sel in (("type", self.types), ("state", self.states), ("area", self.areas)):
            if sel:
                bits.append(f"{name}:{','.join(sorted(sel))}")
        if self.query:
            bits.append(f"text:'{self.query}'")
        return " · ".join(bits) if bits else "none"


@dataclass
class AvailableValues:
    """Distinct values present per filter axis, drawn from the loaded issues."""

    types: set[str] = field(default_factory=set)
    states: set[str] = field(default_factory=set)
    areas: set[str] = field(default_factory=set)


def _ordered(values: set[str], order: list[str]) -> list[str]:
    """Canonical-order the known values, then append any extras alphabetically."""
    known = [v for v in order if v in values]
    extra = sorted(values - set(order))
    return known + extra


class FilterPanel(ModalScreen[FilterState | None]):
    """Multi-select checklist over type / state / area, plus a free-text query.

    space toggles the highlighted option, tab moves between lists, ctrl+s (or
    Apply) commits, escape cancels. Empty lists mean "no constraint on this axis".
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "apply", "Apply"),
    ]

    def __init__(self, current: FilterState, available: AvailableValues) -> None:
        super().__init__()
        self._current = current
        self._available = available

    @staticmethod
    def _selections(values: set[str], order: list[str], selected: set[str]):
        return [(value, value, value in selected) for value in _ordered(values, order)]

    def compose(self) -> ComposeResult:
        avail = self._available
        cur = self._current
        with Vertical(id="filter-box"):
            yield Label("Filter  ·  space toggle · tab move · ctrl+s apply · esc cancel")
            yield Input(value=cur.query, placeholder="text in title or label…", id="filter-text")
            with Horizontal(id="filter-lists"):
                yield SelectionList(
                    *self._selections(avail.types, TYPE_ORDER, cur.types), id="sel-type"
                )
                yield SelectionList(
                    *self._selections(avail.states, STATE_ORDER, cur.states), id="sel-state"
                )
                yield SelectionList(*self._selections(avail.areas, [], cur.areas), id="sel-area")
            with Horizontal(id="filter-buttons"):
                yield Button("Apply (ctrl+s)", id="apply", variant="primary")
                yield Button("Clear all", id="clear")

    def on_mount(self) -> None:
        self.query_one("#sel-type", SelectionList).border_title = "type"
        self.query_one("#sel-state", SelectionList).border_title = "state"
        self.query_one("#sel-area", SelectionList).border_title = "area"
        self.query_one("#filter-text", Input).focus()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.action_apply()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "clear":
            fs = FilterState()
            fs.clear()
            self.dismiss(fs)
        else:
            self.action_apply()

    def action_apply(self) -> None:
        fs = FilterState()
        fs.types = set(self.query_one("#sel-type", SelectionList).selected)
        fs.states = set(self.query_one("#sel-state", SelectionList).selected)
        fs.areas = set(self.query_one("#sel-area", SelectionList).selected)
        fs.query = self.query_one("#filter-text", Input).value.strip()
        self.dismiss(fs)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DetailScreen(Screen):
    """Read one proposal and act on it."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "back", "Back"),
        Binding("j", "nav(1)", "Next"),
        Binding("k", "nav(-1)", "Prev"),
        Binding("a", "set_state('approved')", "Approve"),
        Binding("d", "set_state('declined')", "Decline"),
        Binding("h", "set_state('had-comments')", "Had-comments"),
        Binding("c", "comment", "Comment"),
        Binding("w", "web", "Open in browser"),
    ]

    def __init__(self, issue: Issue) -> None:
        super().__init__()
        self.issue = issue
        self._last_md: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Markdown("_loading…_", id="body")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_title()
        self.load_body()
        if REFRESH_SECONDS:
            self.set_interval(REFRESH_SECONDS, self.load_body)

    def _refresh_title(self) -> None:
        i = self.issue
        self.title = f"#{i.number}  [{i.state}]  {i.title}"
        self.sub_title = f"{i.area} · {i.enforcer_text} · priority:{i.priority}"

    @staticmethod
    def _linkify(text: str) -> str:
        """Make `#123` issue references clickable (href `issue:123`)."""
        return ISSUE_REF.sub(r"[#\1](issue:\1)", text)

    @classmethod
    def _format_detail(cls, detail: IssueDetail) -> str:
        body = cls._linkify(detail.body) if detail.body else "_(no body)_"
        parts = [body, "---", f"## Comments ({len(detail.comments)})"]
        if not detail.comments:
            parts.append("_no comments yet_")
        for c in detail.comments:
            parts.append(f"**@{c.author}** · {c.when}\n\n{cls._linkify(c.body)}")
        return "\n\n".join(parts)

    @work(thread=True, exclusive=True, group="load_body")
    def load_body(self) -> None:
        number = self.issue.number
        try:
            md = self._format_detail(gh.issue_detail(number))
        except gh.GhError as exc:
            md = f"**error loading issue:** {exc}"
        # Ignore stale responses (issue changed while this fetch was in flight)
        # and skip redundant updates so polling doesn't flicker / reset scroll.
        if number != self.issue.number or md == self._last_md:
            return
        self._last_md = md
        self.app.call_from_thread(self.query_one("#body", Markdown).update, md)

    def action_back(self) -> None:
        self.app.pop_screen()

    def _show_issue(self, issue: Issue) -> None:
        """Switch the detail view to another issue and (re)load its body."""
        self.issue = issue
        self._last_md = None
        self._refresh_title()
        self.query_one("#body", Markdown).update("_loading…_")
        self.load_body()

    def action_nav(self, delta: int) -> None:
        nxt = self.app.neighbor(self.issue.number, delta)
        if nxt is None:
            self.notify("end of list" if delta > 0 else "start of list")
            return
        self._show_issue(nxt)

    def on_text_selected(self, event: events.TextSelected) -> None:
        """Auto-copy any selected text in the proposal body to the clipboard.

        The screen posts `TextSelected` on mouse-up; a plain click clears the
        selection first, so only copy/notify when there's actually text.
        """
        selected = self.get_selected_text()
        if selected:
            self.app.copy_to_clipboard(selected)
            self.notify("copied selection to clipboard")

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Follow clicked links: `issue:N` jumps in-app; http(s) opens a browser."""
        href = event.href
        if href.startswith("issue:"):
            try:
                number = int(href.split(":", 1)[1])
            except ValueError:
                return
            if number == self.issue.number:
                return
            issue = self.app.find_issue(number)
            if issue is None:
                self.notify(f"#{number} is not in the loaded list")
                return
            self._show_issue(issue)
        elif href.startswith(("http://", "https://")):
            webbrowser.open(href)

    @work(thread=True)
    def action_set_state(self, new_state: str) -> None:
        try:
            gh.set_state(self.issue, new_state)
        except gh.GhError as exc:
            self.app.call_from_thread(self.notify, f"failed: {exc}", severity="error")
            return
        self.issue.state = new_state
        self.issue.is_open = new_state != "declined"
        self.issue.labels = [
            name for name in self.issue.labels if not name.startswith("state:")
        ] + [f"state:{new_state}"]
        self.app.call_from_thread(self._refresh_title)
        self.app.call_from_thread(self.app.refresh_row, self.issue)
        self.app.call_from_thread(self.notify, f"#{self.issue.number} → {new_state}")

    def action_comment(self) -> None:
        def after(body: str | None) -> None:
            if body:
                self._post_comment(body)

        self.app.push_screen(CommentModal(), after)

    @work(thread=True)
    def _post_comment(self, body: str) -> None:
        try:
            gh.add_comment(self.issue.number, body)
        except gh.GhError as exc:
            self.app.call_from_thread(self.notify, f"comment failed: {exc}", severity="error")
            return
        self.app.call_from_thread(self.notify, "comment added")
        self.app.call_from_thread(self.load_body)  # refresh to show the new comment

    def action_web(self) -> None:
        webbrowser.open(gh.web_url(self.issue.number))


class ReviewApp(App):
    """Top-level review app: the issue list."""

    CSS = """
    #comment-box, #filter-box { align: center middle; width: 80%; height: auto;
        background: $panel; border: tall $primary; padding: 1; }
    #comment-text { height: 12; }
    #filter-lists { height: 12; }
    #filter-lists SelectionList { width: 1fr; border: round $primary; }
    #filter-buttons { height: auto; align: center middle; }
    #filter-buttons Button { margin: 1 2 0 2; }
    DataTable { height: 1fr; }
    """

    # Maps a clicked column key -> sort mode. Keep in sync with compose()'s columns.
    COLUMN_SORT: ClassVar[dict[str, str]] = {
        "number": "number",
        "pri": "pri",
        "state": "state",
        "area": "area",
        "enforcer": "enforcer",
        "comments": "comments",
        "updated": "activity",
        "title": "title",
    }

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "open", "Open"),
        Binding("o", "open", "Open"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("f", "filter", "Filter"),
        Binding("slash", "filter", "Filter", show=False),
        Binding("x", "clear_filter", "Clear filter"),
        Binding("S", "cycle_sort", "Sort"),
        Binding("r", "reload", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.issues: list[Issue] = []
        self.filters = FilterState()
        self.sort_mode: str = "pri"
        self.sort_desc: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        table = DataTable(cursor_type="row", zebra_stripes=True)
        table.add_column("#", key="number")
        table.add_column("pri", key="pri")
        table.add_column("state", key="state")
        table.add_column("area", key="area")
        table.add_column("enforcer", key="enforcer")
        table.add_column("cmts", key="comments")
        table.add_column("activity", key="updated")
        table.add_column("title", key="title")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).focus()
        self.reload()
        if REFRESH_SECONDS:
            self.set_interval(REFRESH_SECONDS, self.reload)

    @work(thread=True, exclusive=True, group="reload")
    def reload(self) -> None:
        try:
            issues = gh.list_issues()
        except gh.GhError as exc:
            self.app.call_from_thread(self.notify, f"gh error: {exc}", severity="error")
            return
        self.issues = issues
        self.app.call_from_thread(self._rebuild)

    @staticmethod
    def _sort_key(mode: str):
        """Return a key function over Issue for the given sort mode."""
        if mode == "activity":
            return lambda i: (i.updated_at, i.number)
        if mode == "comments":
            return lambda i: (i.comment_count, i.number)
        if mode == "number":
            return lambda i: i.number
        if mode == "state":
            return lambda i: (i.state, i.number)
        if mode == "area":
            return lambda i: (i.area, i.number)
        if mode == "enforcer":
            return lambda i: (i.enforcer_text, i.number)
        if mode == "title":
            return lambda i: (i.title.lower(), i.number)
        # "pri": high priority first, then issue number
        return lambda i: (PRIORITY_RANK.get(i.priority, 1), i.number)

    def _visible(self) -> list[Issue]:
        matched = [i for i in self.issues if self.filters.matches(i)]
        matched.sort(key=self._sort_key(self.sort_mode), reverse=self.sort_desc)
        return matched

    def _available(self) -> AvailableValues:
        """Distinct non-empty values per axis, drawn from the loaded issues."""
        return AvailableValues(
            types={i.type for i in self.issues if i.type},
            states={i.state for i in self.issues if i.state},
            areas={i.area for i in self.issues if i.area},
        )

    def _rebuild(self) -> None:
        table = self.query_one(DataTable)
        prev_key = self._cursor_row_key(table)
        table.clear()
        visible = self._visible()
        for i in visible:
            table.add_row(
                str(i.number),
                _styled(i.priority, PRIORITY_STYLE.get(i.priority, "")),
                _styled(i.state, STATE_STYLE.get(i.state, "")),
                _styled(i.area, _area_style(i.area)),
                i.enforcer_text,
                _styled(str(i.comment_count), "" if i.comment_count else "dim"),
                _relative_activity(i.updated_at),
                i.title,
                key=str(i.number),
            )
        self._restore_cursor(table, prev_key)
        arrow = "↓" if self.sort_desc else "↑"
        self.sub_title = (
            f"{len(visible)}/{len(self.issues)} · "
            f"sort:{SORT_LABEL.get(self.sort_mode, self.sort_mode)}{arrow} · "
            f"filter:{self.filters.summary()}"
        )
        self.title = "proposal review"

    def refresh_row(self, issue: Issue) -> None:
        self._rebuild()

    @staticmethod
    def _cursor_row_key(table: DataTable) -> str | None:
        """Return the row key under the cursor so reloads don't lose your place."""
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    @staticmethod
    def _restore_cursor(table: DataTable, key: str | None) -> None:
        if key is None:
            return
        with contextlib.suppress(Exception):
            table.move_cursor(row=table.get_row_index(key))

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def find_issue(self, number: int) -> Issue | None:
        """Return a loaded issue by number, regardless of the current filter."""
        return next((i for i in self.issues if i.number == number), None)

    def neighbor(self, number: int, delta: int) -> Issue | None:
        """Return the next/prev issue in the current filtered+sorted view."""
        vis = self._visible()
        nums = [i.number for i in vis]
        if number not in nums:
            return None
        target = nums.index(number) + delta
        return vis[target] if 0 <= target < len(vis) else None

    def _open_issue(self, key: str | None) -> None:
        issue = next((i for i in self.issues if str(i.number) == key), None)
        if issue:
            self.push_screen(DetailScreen(issue))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # DataTable consumes `enter` and posts this instead of firing the app binding.
        self._open_issue(event.row_key.value)

    def action_open(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        self._open_issue(key)

    def action_filter(self) -> None:
        def after(value: FilterState | None) -> None:
            if value is not None:
                self.filters = value
                self._rebuild()

        self.push_screen(FilterPanel(self.filters, self._available()), after)

    def action_clear_filter(self) -> None:
        self.filters.clear()
        self._rebuild()

    def _set_sort(self, mode: str) -> None:
        """Select a sort mode; re-selecting the same mode flips direction."""
        if mode == self.sort_mode:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_mode = mode
            self.sort_desc = mode in SORT_DEFAULT_DESC
        self._rebuild()

    def action_cycle_sort(self) -> None:
        cur = SORT_CYCLE.index(self.sort_mode) if self.sort_mode in SORT_CYCLE else -1
        self._set_sort(SORT_CYCLE[(cur + 1) % len(SORT_CYCLE)])

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        mode = self.COLUMN_SORT.get(event.column_key.value)
        if mode:
            self._set_sort(mode)

    def action_reload(self) -> None:
        self.reload()


def _plain() -> int:
    """Non-TUI smoke test: print the list (priority-sorted, as gh returns it)."""
    issues = gh.list_issues()
    print(f"{len(issues)} issues on {gh.REPO} (sorted by priority):\n")
    for i in issues:
        print(
            f"  #{i.number:<4} {i.priority:<7} {i.state:<13} {i.area:<14} "
            f"{i.enforcer_text:<22} {i.comment_count:>3}c {i.updated_short:<11} {i.title[:50]}"
        )
    return 0


def main() -> int:
    if "--plain" in sys.argv:
        return _plain()
    ReviewApp().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
