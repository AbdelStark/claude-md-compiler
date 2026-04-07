"""In-memory state for the `cldc` TUI.

The TUI keeps a single `TuiState` dataclass that summarizes everything the
app needs to render: the discovered repo, the parsed policy, the lockfile
metadata, the current runtime evidence being composed, and the most recent
check report. Mutations go through the small set of loader functions below
so reactive updates in `app.py` have a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cldc.compiler.policy_compiler import (
    CompiledPolicy,
    DoctorReport,
    compile_repo_policy,
    doctor_repo_policy,
)
from cldc.errors import CldcError
from cldc.ingest.discovery import LOCKFILE_PATH, discover_policy_repo
from cldc.ingest.source_loader import SourceBundle, load_policy_sources
from cldc.parser.rule_parser import ParsedPolicy, parse_rule_documents
from cldc.runtime.evaluator import CheckReport, check_repo_policy


@dataclass
class Evidence:
    """User-composed runtime evidence for the next `cldc check` run."""

    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)

    def copy(self) -> Evidence:
        return Evidence(
            read_paths=list(self.read_paths),
            write_paths=list(self.write_paths),
            commands=list(self.commands),
            claims=list(self.claims),
        )

    def is_empty(self) -> bool:
        return not (self.read_paths or self.write_paths or self.commands or self.claims)


@dataclass
class TuiState:
    """Snapshot of everything the TUI needs to render."""

    repo_root: Path
    discovered: bool = False
    bundle: SourceBundle | None = None
    parsed: ParsedPolicy | None = None
    lockfile_exists: bool = False
    lockfile_path: Path | None = None
    lockfile_mtime: float | None = None
    compile_metadata: CompiledPolicy | None = None
    doctor: DoctorReport | None = None
    evidence: Evidence = field(default_factory=Evidence)
    report: CheckReport | None = None
    last_error: str | None = None

    @property
    def rule_count(self) -> int:
        return len(self.parsed.rules) if self.parsed else 0

    @property
    def source_count(self) -> int:
        return len(self.bundle.sources) if self.bundle else 0

    @property
    def default_mode(self) -> str | None:
        return self.parsed.default_mode if self.parsed else None

    def rule_by_id(self, rule_id: str) -> dict[str, Any] | None:
        if self.parsed is None:
            return None
        for rule in self.parsed.rules:
            if rule.rule_id == rule_id:
                return rule.to_dict()
        return None


def discover_state(repo_root: Path | str) -> TuiState:
    """Walk from `repo_root`, load sources, parse rules, and snapshot everything."""

    root = Path(repo_root).resolve()
    state = TuiState(repo_root=root)

    try:
        discovery = discover_policy_repo(root)
    except FileNotFoundError as exc:
        state.last_error = f"Repo discovery failed: {exc}"
        return state

    if not discovery.discovered:
        state.last_error = discovery.warnings[0] if discovery.warnings else "no policy markers found"
        return state

    state.repo_root = Path(discovery.repo_root)
    state.discovered = True

    try:
        state.bundle = load_policy_sources(state.repo_root)
    except CldcError as exc:
        state.last_error = f"Source load failed: {exc}"
        return state

    try:
        state.parsed = parse_rule_documents(state.bundle)
    except CldcError as exc:
        state.last_error = f"Rule parse failed: {exc}"
        return state

    lockfile = state.repo_root / LOCKFILE_PATH
    state.lockfile_path = lockfile
    state.lockfile_exists = lockfile.is_file()
    state.lockfile_mtime = lockfile.stat().st_mtime if state.lockfile_exists else None

    try:
        state.doctor = doctor_repo_policy(state.repo_root)
    except CldcError as exc:
        state.last_error = f"Doctor failed: {exc}"

    return state


def recompile_state(state: TuiState) -> TuiState:
    """Run `compile_repo_policy` and refresh the lockfile metadata in-place."""

    try:
        state.compile_metadata = compile_repo_policy(state.repo_root)
        state.last_error = None
    except CldcError as exc:
        state.last_error = f"Compile failed: {exc}"
        return state

    lockfile = state.repo_root / LOCKFILE_PATH
    state.lockfile_path = lockfile
    state.lockfile_exists = lockfile.is_file()
    state.lockfile_mtime = lockfile.stat().st_mtime if state.lockfile_exists else None

    # Refresh parsed bundle to reflect any on-disk changes.
    try:
        state.bundle = load_policy_sources(state.repo_root)
        state.parsed = parse_rule_documents(state.bundle)
    except CldcError as exc:
        state.last_error = f"Source reload failed after compile: {exc}"

    try:
        state.doctor = doctor_repo_policy(state.repo_root)
    except CldcError as exc:
        state.last_error = f"Doctor failed after compile: {exc}"

    return state


def run_check(state: TuiState) -> TuiState:
    """Evaluate the current evidence against the compiled lockfile."""

    if not state.lockfile_exists:
        state.last_error = "No compiled lockfile yet; press C to compile first."
        state.report = None
        return state

    try:
        state.report = check_repo_policy(
            state.repo_root,
            read_paths=list(state.evidence.read_paths),
            write_paths=list(state.evidence.write_paths),
            commands=list(state.evidence.commands),
            claims=list(state.evidence.claims),
        )
        state.last_error = None
    except CldcError as exc:
        state.last_error = f"Check failed: {exc}"
        state.report = None
    except FileNotFoundError as exc:
        state.last_error = str(exc)
        state.report = None

    return state
