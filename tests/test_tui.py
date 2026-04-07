"""Smoke tests for the cldc TUI using Textual's Pilot.

These tests exercise the app in headless mode: they mount it against a
real fixture repo, verify the widgets render, drive keybindings through
the Pilot, and assert that the reactive state updates correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.tui.app import CldcApp
from cldc.tui.state import Evidence, discover_state, recompile_state, run_check
from cldc.tui.widgets import DecisionPanel, DetailPane, RepoBar, RulesPane, SourcesPane


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Copy the canonical fixture repo into `tmp_path` and compile it."""

    source = Path(__file__).parent / "fixtures" / "repo_a"
    target = tmp_path / "repo"
    target.mkdir()
    for entry in source.rglob("*"):
        if entry.is_file():
            destination = target / entry.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
    compile_repo_policy(target)
    return target


# --- state module tests -----------------------------------------------------


def test_discover_state_loads_sources_and_rules(fixture_repo: Path) -> None:
    state = discover_state(fixture_repo)

    assert state.discovered is True
    assert state.bundle is not None
    assert state.parsed is not None
    assert state.rule_count == 3
    assert state.source_count == 4
    assert state.default_mode == "warn"
    assert state.lockfile_exists is True
    assert state.last_error is None


def test_discover_state_reports_missing_markers(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    state = discover_state(empty)

    assert state.discovered is False
    assert state.last_error is not None


def test_run_check_populates_report(fixture_repo: Path) -> None:
    state = discover_state(fixture_repo)
    state.evidence = Evidence(write_paths=["src/main.py"])

    updated = run_check(state)

    assert updated.report is not None
    assert updated.report.decision == "warn"
    assert updated.report.violation_count == 2
    assert updated.last_error is None


def test_run_check_without_lockfile_errors(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n",
        encoding="utf-8",
    )
    state = discover_state(tmp_path)
    updated = run_check(state)

    assert updated.report is None
    assert updated.last_error is not None
    assert "compile" in updated.last_error.lower()


def test_recompile_state_refreshes_lockfile(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n",
        encoding="utf-8",
    )
    state = discover_state(tmp_path)
    assert state.lockfile_exists is False

    updated = recompile_state(state)

    assert updated.lockfile_exists is True
    assert updated.compile_metadata is not None
    assert updated.compile_metadata.rule_count == 1


def test_tui_state_rule_by_id_returns_serialized_dict(fixture_repo: Path) -> None:
    state = discover_state(fixture_repo)
    rule = state.rule_by_id("generated-lock")

    assert rule is not None
    assert rule["kind"] == "deny_write"
    assert rule["paths"] == ["generated/**"]


def test_tui_state_evidence_is_empty_detects_empty_vs_populated() -> None:
    assert Evidence().is_empty() is True
    assert Evidence(write_paths=["src/foo.py"]).is_empty() is False


# --- Pilot-driven app smoke tests ------------------------------------------


@pytest.mark.asyncio
async def test_app_mounts_and_renders_repo_state(fixture_repo: Path) -> None:
    app = CldcApp(repo_root=fixture_repo)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.state is not None
        assert app.state.discovered is True
        assert app.state.rule_count == 3

        repo_bar = app.query_one(RepoBar)
        assert repo_bar.state is not None

        rules_pane = app.query_one(RulesPane)
        assert rules_pane.state is not None

        sources_pane = app.query_one(SourcesPane)
        assert sources_pane.state is not None

        detail_pane = app.query_one(DetailPane)
        assert detail_pane.state is not None

        decision = app.query_one(DecisionPanel)
        assert decision.state is not None


@pytest.mark.asyncio
async def test_app_run_check_binding_populates_report(fixture_repo: Path) -> None:
    app = CldcApp(repo_root=fixture_repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.state is not None

        # Populate evidence directly on the state and trigger the binding.
        app.state.evidence.write_paths = ["src/main.py"]
        await pilot.press("r")
        await pilot.pause()

        assert app.state.report is not None
        assert app.state.report.decision == "warn"
        assert app.state.report.violation_count == 2


@pytest.mark.asyncio
async def test_app_compile_binding_refreshes_lockfile(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n",
        encoding="utf-8",
    )

    app = CldcApp(repo_root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.state is not None
        assert app.state.lockfile_exists is False

        await pilot.press("c")
        await pilot.pause()

        assert app.state.lockfile_exists is True
        assert app.state.rule_count == 1


@pytest.mark.asyncio
async def test_app_clear_evidence_binding_resets_inputs(fixture_repo: Path) -> None:
    app = CldcApp(repo_root=fixture_repo)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.state is not None
        app.state.evidence.write_paths = ["src/main.py"]
        app.state.evidence.commands = ["pytest -q"]
        run_check(app.state)
        assert app.state.report is not None

        await pilot.press("ctrl+l")
        await pilot.pause()

        assert app.state.evidence.write_paths == []
        assert app.state.evidence.commands == []
        assert app.state.report is None


def test_tui_subcommand_reachable_from_cli_help() -> None:
    """The `tui` subcommand must be advertised in `cldc --help`."""

    from cldc.cli.main import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "tui" in help_text
