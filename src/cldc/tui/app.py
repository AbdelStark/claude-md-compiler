"""Textual application for the cldc TUI.

`run_tui(repo)` is the entry point invoked by `cldc tui`. It builds a
`CldcApp`, discovers the repo, and blocks until the user exits.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from cldc import __version__
from cldc.presets import list_presets, load_preset
from cldc.tui.state import TuiState, discover_state, recompile_state, run_check
from cldc.tui.widgets import (
    DecisionPanel,
    DetailPane,
    EvidenceForm,
    RepoBar,
    RulesPane,
    SourcesPane,
)

_TCSS_PATH = Path(__file__).with_name("styles.tcss")


class PresetModal(ModalScreen[None]):
    """Side-by-side preset picker + content viewer."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        box = Vertical(classes="modal-box")
        with box:
            yield Label("Bundled presets", classes="modal-title")
            with Horizontal():
                list_view = ListView(id="preset-list")
                yield list_view
                yield Static("", id="preset-content")
        yield box

    def on_mount(self) -> None:
        list_view = self.query_one("#preset-list", ListView)
        presets = list_presets()
        for preset in presets:
            list_view.append(ListItem(Label(preset.name), id=f"preset-{preset.name}"))
        if presets:
            list_view.index = 0
            self._show(presets[0].name)
        else:
            self.query_one("#preset-content", Static).update(
                "No presets are bundled with this cldc version.",
            )

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        name = event.item.id.removeprefix("preset-")
        if name:
            self._show(name)

    def _show(self, name: str) -> None:
        try:
            content = load_preset(name)
        except Exception as exc:
            content = f"Failed to load preset {name!r}: {exc}"
        self.query_one("#preset-content", Static).update(content)


class DoctorModal(ModalScreen[None]):
    """Lightweight doctor summary popover."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def __init__(self, body: str) -> None:
        super().__init__()
        self._body = body

    def compose(self) -> ComposeResult:
        box = Vertical(classes="modal-box")
        with box:
            yield Label("Doctor report", classes="modal-title")
            yield Static(self._body)
        yield box


class CldcApp(App[None]):
    """Interactive policy explorer for cldc."""

    CSS_PATH = _TCSS_PATH
    TITLE = "cldc"
    SUB_TITLE = f"v{__version__}  ·  policy explorer"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "compile", "Compile"),
        Binding("r", "run_check", "Run check"),
        Binding("d", "doctor", "Doctor"),
        Binding("p", "presets", "Presets"),
        Binding("R", "reload", "Reload sources"),
        Binding("ctrl+l", "clear_evidence", "Clear evidence"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("?", "help", "Help", show=True),
    ]

    state: reactive[TuiState | None] = reactive(None)
    selected_rule_id: reactive[str | None] = reactive(None)

    def __init__(self, repo_root: Path | str = ".") -> None:
        super().__init__()
        self._initial_repo = Path(repo_root)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RepoBar()
        with Horizontal(id="browser"):
            yield SourcesPane()
            yield RulesPane()
            yield DetailPane()
        yield EvidenceForm()
        yield DecisionPanel()
        yield Footer()

    def on_mount(self) -> None:
        new_state = discover_state(self._initial_repo)
        self.state = new_state
        if new_state.last_error:
            self.notify(new_state.last_error, title="cldc", severity="error", timeout=8)

    def watch_state(self, state: TuiState | None) -> None:
        if state is None:
            return
        self.query_one(RepoBar).state = state
        self.query_one(SourcesPane).state = state
        self.query_one(RulesPane).state = state
        detail = self.query_one(DetailPane)
        detail.state = state
        detail.selected_rule_id = self.selected_rule_id
        self.query_one(DecisionPanel).state = state

    def watch_selected_rule_id(self, rule_id: str | None) -> None:
        detail = self.query_one(DetailPane)
        detail.selected_rule_id = rule_id

    # --- messages from widgets ---------------------------------------

    def on_rules_pane_rule_selected(self, message: RulesPane.RuleSelected) -> None:
        self.selected_rule_id = message.rule_id

    def on_evidence_form_evidence_changed(self, message: EvidenceForm.EvidenceChanged) -> None:
        state = self.state
        if state is None:
            return
        state.evidence.read_paths = message.read_paths
        state.evidence.write_paths = message.write_paths
        state.evidence.commands = message.commands
        state.evidence.claims = message.claims
        # Mutating the dataclass in place does not re-trigger reactive watchers,
        # so leave the banner/prompt where it is until the user presses R.

    # --- actions ------------------------------------------------------

    def action_compile(self) -> None:
        state = self.state
        if state is None:
            return
        updated = recompile_state(state)
        self.state = updated
        # Force the reactive watcher to fire even when the identity is unchanged.
        self.mutate_reactive(CldcApp.state)
        if updated.last_error:
            self.notify(updated.last_error, title="compile", severity="error", timeout=6)
            return
        compiled = updated.compile_metadata
        if compiled is not None:
            self.notify(
                f"Compiled {compiled.rule_count} rules from {compiled.source_count} sources.",
                title="compile",
                severity="information",
                timeout=3,
            )

    def action_run_check(self) -> None:
        state = self.state
        if state is None:
            return
        updated = run_check(state)
        self.state = updated
        self.mutate_reactive(CldcApp.state)
        if updated.last_error:
            self.notify(updated.last_error, title="check", severity="error", timeout=6)
            return
        if updated.report is not None:
            decision = updated.report.decision.upper()
            severity = "information"
            if updated.report.decision == "block":
                severity = "error"
            elif updated.report.decision == "warn":
                severity = "warning"
            self.notify(
                f"Decision: {decision} ({updated.report.violation_count} violation(s))",
                title="check",
                severity=severity,
                timeout=3,
            )

    def action_reload(self) -> None:
        state = self.state
        if state is None:
            return
        new_state = discover_state(state.repo_root)
        self.state = new_state
        self.mutate_reactive(CldcApp.state)
        if new_state.last_error:
            self.notify(new_state.last_error, title="reload", severity="error", timeout=6)
        else:
            self.notify(
                f"Reloaded {new_state.source_count} sources / {new_state.rule_count} rules.",
                title="reload",
                severity="information",
                timeout=3,
            )

    def action_doctor(self) -> None:
        state = self.state
        if state is None:
            return
        body = _format_doctor_report(state)
        self.push_screen(DoctorModal(body))

    def action_presets(self) -> None:
        self.push_screen(PresetModal())

    def action_clear_evidence(self) -> None:
        form = self.query_one(EvidenceForm)
        for input_id in ("#reads-input", "#writes-input", "#commands-input", "#claims-input"):
            try:
                form.query_one(input_id).value = ""  # type: ignore[attr-defined]
            except Exception:
                continue
        state = self.state
        if state is not None:
            state.evidence.read_paths = []
            state.evidence.write_paths = []
            state.evidence.commands = []
            state.evidence.claims = []
            state.report = None
            self.mutate_reactive(CldcApp.state)
        self.notify("Cleared evidence.", title="cldc", severity="information", timeout=2)

    def action_help(self) -> None:
        self.notify(
            "C: compile  ·  R: run check  ·  D: doctor  ·  P: presets  ·  Shift+R: reload sources  ·  Ctrl+L: clear evidence  ·  Q: quit",
            title="help",
            severity="information",
            timeout=8,
        )


def _format_doctor_report(state: TuiState) -> str:
    doctor = state.doctor
    if doctor is None:
        return "Doctor has not been run yet for this repo."

    lines = [
        f"repo_root   {doctor.repo_root}",
        f"sources     {doctor.source_count}",
        f"rules       {doctor.rule_count}",
        f"mode        {doctor.default_mode or '(none)'}",
        f"lockfile    {'present' if doctor.lockfile_exists else 'missing'}",
    ]
    if doctor.source_digest:
        lines.append(f"digest      {doctor.source_digest[:16]}...")
    if doctor.lockfile_schema:
        lines.append(f"schema      {doctor.lockfile_schema}")
    if doctor.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"  · {item}" for item in doctor.warnings)
    if doctor.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"  · {item}" for item in doctor.errors)
    if doctor.next_action:
        lines.append("")
        lines.append(f"next action: {doctor.next_action}")
    return "\n".join(lines)


def run_tui(repo_root: Path | str = ".") -> int:
    """Launch the interactive TUI against `repo_root`."""

    app = CldcApp(repo_root=repo_root)
    app.run()
    return 0
