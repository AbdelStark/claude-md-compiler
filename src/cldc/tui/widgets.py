"""Custom widgets for the cldc TUI.

Each widget is a thin wrapper around Textual's built-ins, specialized for
one region of the layout. They communicate with `CldcApp` via messages
(posted with `self.post_message`) so the app can own all state mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, Static, Tree
from textual.widgets.tree import TreeNode

from cldc.tui.state import TuiState

_MODE_SORT = {"block": 0, "fix": 1, "warn": 2, "observe": 3}


# --- Repo bar ---------------------------------------------------------------


class RepoBar(Static):
    """Top-of-screen strip showing repo root, doctor status, and lockfile age."""

    state: reactive[TuiState | None] = reactive(None, layout=True)

    def __init__(self) -> None:
        super().__init__(id="repo-bar")

    def compose(self) -> ComposeResult:
        yield Label("cldc — starting...", id="repo-path")
        yield Label("", classes="status-label", id="repo-status")
        yield Label("", classes="status-label", id="repo-lockfile")
        yield Label("", classes="status-label", id="repo-rules")

    def watch_state(self, state: TuiState | None) -> None:
        if state is None:
            return
        path_label = self.query_one("#repo-path", Label)
        status_label = self.query_one("#repo-status", Label)
        lockfile_label = self.query_one("#repo-lockfile", Label)
        rules_label = self.query_one("#repo-rules", Label)

        path_label.update(f"Repo: {state.repo_root}")

        if state.doctor is None:
            status_label.update("status: unknown")
            status_label.set_classes("status-label status-missing")
        elif state.doctor.errors:
            status_label.update(f"status: broken ({len(state.doctor.errors)})")
            status_label.set_classes("status-label status-broken")
        elif state.doctor.warnings:
            status_label.update(f"status: drifted ({len(state.doctor.warnings)})")
            status_label.set_classes("status-label status-drifted")
        else:
            status_label.update("status: healthy")
            status_label.set_classes("status-label status-healthy")

        if state.lockfile_exists:
            lockfile_label.update("lockfile: present")
            lockfile_label.set_classes("status-label status-healthy")
        else:
            lockfile_label.update("lockfile: missing")
            lockfile_label.set_classes("status-label status-missing")

        rules_label.update(f"rules: {state.rule_count} / sources: {state.source_count}")
        rules_label.set_classes("status-label")


# --- Sources pane -----------------------------------------------------------


class SourcesPane(Vertical):
    """Left-hand pane: grouped tree of discovered policy sources."""

    state: reactive[TuiState | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__(classes="pane", id="sources-pane")
        self._tree: Tree[str] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Sources", classes="pane-title")
        tree: Tree[str] = Tree("policy", id="sources-tree")
        tree.show_root = False
        tree.guide_depth = 3
        self._tree = tree
        yield tree

    def watch_state(self, state: TuiState | None) -> None:
        if state is None or self._tree is None:
            return
        tree = self._tree
        tree.clear()
        root = tree.root

        if state.bundle is None:
            root.add_leaf("(no sources discovered)")
            return

        grouped: dict[str, list[Any]] = {}
        for source in state.bundle.sources:
            grouped.setdefault(source.kind, []).append(source)

        kind_titles = {
            "claude_md": "CLAUDE.md",
            "inline_block": "inline cldc blocks",
            "compiler_config": "compiler config",
            "preset": "presets (extends:)",
            "policy_file": "policy fragments",
        }
        for kind in ["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]:
            if kind not in grouped:
                continue
            group_node: TreeNode[str] = root.add(kind_titles[kind], expand=True)
            for source in grouped[kind]:
                label = source.block_id or source.path
                group_node.add_leaf(label)


# --- Rules pane -------------------------------------------------------------


@dataclass
class RuleRow:
    rule_id: str
    kind: str
    mode: str
    message: str


class RulesPane(Vertical):
    """Middle pane: sortable table of rules with mode badges."""

    state: reactive[TuiState | None] = reactive(None)

    class RuleSelected(Message):
        """Posted when the focused row in the rules table changes."""

        def __init__(self, rule_id: str | None) -> None:
            super().__init__()
            self.rule_id = rule_id

    def __init__(self) -> None:
        super().__init__(classes="pane", id="rules-pane")
        self._table: DataTable[str] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Rules", classes="pane-title")
        table: DataTable[str] = DataTable(id="rules-table", cursor_type="row", zebra_stripes=True)
        table.add_column("Rule", width=28, key="rule")
        table.add_column("Kind", width=16, key="kind")
        table.add_column("Mode", width=8, key="mode")
        self._table = table
        yield table

    def watch_state(self, state: TuiState | None) -> None:
        if state is None or self._table is None:
            return
        table = self._table
        table.clear()

        if state.parsed is None or not state.parsed.rules:
            return

        default_mode = state.parsed.default_mode
        rows: list[RuleRow] = []
        for rule in state.parsed.rules:
            effective_mode = rule.mode or default_mode
            rows.append(RuleRow(rule_id=rule.rule_id, kind=rule.kind, mode=effective_mode, message=rule.message))
        rows.sort(key=lambda r: (_MODE_SORT.get(r.mode, 99), r.rule_id))

        for row in rows:
            icon = "●" if row.mode in {"block", "fix"} else "○"
            mode_label = _mode_cell(row.mode)
            table.add_row(f"{icon} {row.rule_id}", row.kind, mode_label, key=row.rule_id)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key
        rule_id = str(key.value) if key and key.value is not None else None
        self.post_message(self.RuleSelected(rule_id))


def _mode_cell(mode: str) -> str:
    """Return a plain-text mode label (Textual DataTable does not render CSS classes on cells)."""

    return mode.upper()


# --- Detail pane ------------------------------------------------------------


class DetailPane(Vertical):
    """Right pane: rule detail (or instructions when nothing is selected)."""

    state: reactive[TuiState | None] = reactive(None)
    selected_rule_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__(classes="pane", id="detail-pane")
        self._body: Static | None = None

    def compose(self) -> ComposeResult:
        yield Label("Detail", classes="pane-title")
        body = Static(
            "Select a rule to see its definition.\n\nPress [b]c[/b] to compile, "
            "[b]r[/b] to run a check, [b]p[/b] to browse presets, [b]d[/b] to run doctor.",
            id="detail-view",
        )
        self._body = body
        yield body

    def watch_selected_rule_id(self, rule_id: str | None) -> None:
        self._refresh()

    def watch_state(self, _state: TuiState | None) -> None:
        self._refresh()

    def _refresh(self) -> None:
        if self._body is None:
            return

        state = self.state
        if state is None:
            self._body.update("Loading...")
            return
        if state.last_error:
            self._body.update(f"[b $error]Error[/] {state.last_error}")
            return
        if not state.discovered:
            self._body.update("No policy sources discovered.\nPoint cldc at a repo with a CLAUDE.md.")
            return
        if self.selected_rule_id is None:
            default_mode = state.default_mode or "unknown"
            source_count = state.source_count
            lines = [
                "[b $accent]cldc[/]  interactive policy explorer",
                "",
                f"default mode: [b]{default_mode}[/]",
                f"sources: [b]{source_count}[/]",
                f"rules: [b]{state.rule_count}[/]",
                "",
                "Select a rule on the left to see its full definition,",
                "or fill in evidence below and press [b]r[/] to run a check.",
            ]
            self._body.update("\n".join(lines))
            return

        rule = state.rule_by_id(self.selected_rule_id)
        if rule is None:
            self._body.update(f"Rule [b]{self.selected_rule_id}[/] is not in the current policy.")
            return
        self._body.update(_render_rule_detail(rule))


def _render_rule_detail(rule: dict[str, Any]) -> str:
    mode = rule.get("mode") or "(default)"
    kind = rule.get("kind", "<unknown>")
    mode_color = {
        "block": "$error",
        "fix": "$error",
        "warn": "$warning",
        "observe": "$text-muted",
    }.get(mode, "$text")

    lines = [
        f"[b $accent]{rule.get('id', '<unknown>')}[/]",
        f"[b]{kind}[/]  [$text-muted]·[/]  [b {mode_color}]{mode.upper()}[/]",
        "",
        f"[b]message[/] {rule.get('message', '')}",
    ]

    for field_name in ("paths", "before_paths", "when_paths", "commands", "claims"):
        values = rule.get(field_name)
        if not values:
            continue
        lines.append("")
        lines.append(f"[b]{field_name}[/]")
        for item in values:
            lines.append(f"  · {item}")

    source_path = rule.get("source_path")
    source_block_id = rule.get("source_block_id")
    if source_path or source_block_id:
        lines.append("")
        provenance = source_path or ""
        if source_block_id:
            provenance = f"{provenance}#{source_block_id}" if provenance else str(source_block_id)
        lines.append(f"[$text-muted]provenance: {provenance}[/]")

    return "\n".join(lines)


# --- Evidence form ----------------------------------------------------------


class EvidenceForm(Vertical):
    """Four-row input form for the runtime evidence the user is composing."""

    class EvidenceChanged(Message):
        """Posted whenever a field loses focus with new content."""

        def __init__(
            self,
            *,
            read_paths: list[str],
            write_paths: list[str],
            commands: list[str],
            claims: list[str],
        ) -> None:
            super().__init__()
            self.read_paths = read_paths
            self.write_paths = write_paths
            self.commands = commands
            self.claims = claims

    def __init__(self) -> None:
        super().__init__(id="evidence-form")

    def compose(self) -> ComposeResult:
        yield Label("Evidence (comma-separated per field)", classes="form-title")
        yield _evidence_row("Reads", "reads-input", "docs/spec.md, docs/rfcs/**")
        yield _evidence_row("Writes", "writes-input", "src/main.py, tests/test_main.py")
        yield _evidence_row("Commands", "commands-input", "pytest -q, ruff check")
        yield _evidence_row("Claims", "claims-input", "qa-reviewed, ci-green")

    def current_evidence(self) -> tuple[list[str], list[str], list[str], list[str]]:
        reads = _split_field(self.query_one("#reads-input", Input).value)
        writes = _split_field(self.query_one("#writes-input", Input).value)
        commands = _split_field(self.query_one("#commands-input", Input).value)
        claims = _split_field(self.query_one("#claims-input", Input).value)
        return reads, writes, commands, claims

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._emit_change()

    def on_input_changed(self, _event: Input.Changed) -> None:
        self._emit_change()

    def _emit_change(self) -> None:
        reads, writes, commands, claims = self.current_evidence()
        self.post_message(
            self.EvidenceChanged(
                read_paths=reads,
                write_paths=writes,
                commands=commands,
                claims=claims,
            )
        )


def _evidence_row(label: str, input_id: str, placeholder: str) -> Horizontal:
    row = Horizontal(
        Label(label),
        Input(placeholder=placeholder, id=input_id),
        classes="evidence-row",
    )
    return row


def _split_field(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Decision panel ---------------------------------------------------------


class DecisionPanel(Vertical):
    """Big colored banner plus a scrollable list of violations."""

    state: reactive[TuiState | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__(id="decision-panel")
        self._banner: Static | None = None
        self._body: VerticalScroll | None = None

    def compose(self) -> ComposeResult:
        banner = Static("Press R to run a check", id="decision-banner")
        banner.set_classes("decision-idle")
        self._banner = banner
        yield banner
        body = VerticalScroll(id="decision-body")
        self._body = body
        yield body

    def watch_state(self, state: TuiState | None) -> None:
        if state is None or self._banner is None or self._body is None:
            return

        # Clear any previous rows
        for child in list(self._body.children):
            child.remove()

        if state.last_error and state.report is None:
            self._banner.update(f"ERROR  {state.last_error}")
            self._banner.set_classes("decision-block")
            return

        report = state.report
        if report is None:
            if state.evidence.is_empty():
                self._banner.update("Fill in evidence and press [b]R[/] to run a check")
            else:
                self._banner.update("Press [b]R[/] to run a check against the current evidence")
            self._banner.set_classes("decision-idle")
            return

        decision = report.decision.upper()
        if report.decision == "pass":
            self._banner.update(f"PASS  {report.summary}")
            self._banner.set_classes("decision-pass")
        elif report.decision == "block":
            self._banner.update(f"BLOCK  {report.summary}")
            self._banner.set_classes("decision-block")
        else:
            self._banner.update(f"{decision}  {report.summary}")
            self._banner.set_classes("decision-warn")

        if not report.violations:
            passed = Static(
                "No violations. All rules are satisfied by the current evidence.",
                classes="violation-row passed",
            )
            self._body.mount(passed)
            return

        for violation in report.violations:
            row = _format_violation(violation.to_dict())
            classes = "violation-row " + ("blocking" if violation.mode in {"block", "fix"} else "non-blocking")
            self._body.mount(Static(row, classes=classes))


def _format_violation(violation: dict[str, Any]) -> str:
    mode = violation.get("mode", "warn").upper()
    rule_id = violation.get("rule_id", "<unknown>")
    message = violation.get("message", "")
    recommended = violation.get("recommended_action") or ""
    lines = [f"[{mode}] {rule_id}  —  {message}"]
    if recommended:
        lines.append(f"        next: {recommended}")
    return "\n".join(lines)
