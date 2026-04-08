"""Stateful Claude Code hook adapter for cldc.

The generated `cldc hook generate claude-code` settings snippet delegates to
this module's runtime helpers. The adapter keeps a machine-local session state
of successful Claude Code reads, writes, commands, and explicit claims, then
reuses `check_repo_policy` in three places:

* `PreToolUse` blocks writes that violate true preconditions like
  `deny_write` or blocking `require_read`.
* `PostToolUse` records successful evidence and surfaces concise warn/block
  feedback through Claude's JSON hook output without interrupting the tool flow.
* `PostToolUseFailure` records failed command executions so session state keeps
  success and failure outcomes distinct.
* `Stop` blocks session completion while blocking workflow invariants remain
  unmet (`couple_change`, `require_command`, `require_claim`, etc.).

Claims are explicit by design because Claude Code has no native "claim"
tool event. They can be appended to the active session with `cldc hook claim`.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cldc.errors import CldcError
from cldc.runtime.evaluator import CheckReport, Violation, check_repo_policy

STATE_ROOT_ENV = "CLDC_CLAUDE_STATE_DIR"
WRITE_TOOL_NAMES = {"Edit", "MultiEdit", "Write"}
READ_TOOL_NAMES = {"Read"}
COMMAND_TOOL_NAMES = {"Bash"}
BLOCKING_MODES = {"block", "fix"}
PRE_WRITE_BLOCK_KINDS = {"deny_write", "require_read"}


class ClaudeCodeAdapterError(CldcError):
    """Raised when a Claude Code adapter payload or state file is invalid."""


@dataclass(frozen=True)
class ClaudeCodeCommandResult:
    """One command execution outcome observed during a Claude Code session."""

    command: str
    outcome: str
    tool_use_id: str | None
    exit_code: int | None
    error: str | None
    is_interrupt: bool | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaudeCodeSessionState:
    """Machine-local session evidence accumulated from Claude Code hooks."""

    repo_root: str
    session_id: str
    read_paths: list[str]
    write_paths: list[str]
    commands: list[str]
    claims: list[str]
    command_results: list[ClaudeCodeCommandResult]
    report_path: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["command_results"] = [result.to_dict() for result in self.command_results]
        return payload


@dataclass(frozen=True)
class ClaudeCodeClaimReport:
    """Outcome of appending a claim to the active Claude Code session."""

    repo_root: str
    session_id: str
    claim: str
    claim_count: int
    state_path: str
    report_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HookRuntimeResult:
    """Process-level outcome returned to the CLI's hidden hook runtime."""

    exit_code: int
    stdout: str | None = None
    stderr: str | None = None


def _resolve_repo_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).expanduser().resolve()
    if not root.exists():
        raise ClaudeCodeAdapterError(f"repo path does not exist: {root}")
    if not root.is_dir():
        raise ClaudeCodeAdapterError(f"repo path is not a directory: {root}")
    return root


def _state_root() -> Path:
    override = os.environ.get(STATE_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "cldc"


def _project_key(repo_root: Path) -> str:
    return hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:16]


def _project_dir(repo_root: Path) -> Path:
    return _state_root() / "projects" / _project_key(repo_root)


def _session_state_path(repo_root: Path, session_id: str) -> Path:
    return _project_dir(repo_root) / "sessions" / f"{session_id}.json"


def _session_report_path(repo_root: Path, session_id: str) -> Path:
    return _project_dir(repo_root) / "reports" / f"{session_id}.json"


def _active_session_path(repo_root: Path) -> Path:
    return _project_dir(repo_root) / "active-session.txt"


def _reports_dir(repo_root: Path) -> Path:
    return _project_dir(repo_root) / "reports"


def _empty_state(repo_root: Path, session_id: str) -> ClaudeCodeSessionState:
    return ClaudeCodeSessionState(
        repo_root=str(repo_root),
        session_id=session_id,
        read_paths=[],
        write_paths=[],
        commands=[],
        claims=[],
        command_results=[],
        report_path=str(_session_report_path(repo_root, session_id)),
    )


def _write_state(state: ClaudeCodeSessionState) -> ClaudeCodeSessionState:
    root = Path(state.repo_root)
    path = _session_state_path(root, state.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def load_session_state(repo_root: Path | str, session_id: str) -> ClaudeCodeSessionState:
    """Load one session state file, returning an empty state when missing."""

    root = _resolve_repo_root(repo_root)
    path = _session_state_path(root, session_id)
    if not path.exists():
        return _empty_state(root, session_id)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClaudeCodeAdapterError(f"session state is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ClaudeCodeAdapterError(f"session state must be a JSON object: {path}")

    def _require_list(name: str) -> list[str]:
        value = payload.get(name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ClaudeCodeAdapterError(f"session state field '{name}' must be a list of strings: {path}")
        return value

    raw_command_results = payload.get("command_results", [])
    if not isinstance(raw_command_results, list):
        raise ClaudeCodeAdapterError(f"session state field 'command_results' must be a list: {path}")
    command_results: list[ClaudeCodeCommandResult] = []
    for index, item in enumerate(raw_command_results):
        if not isinstance(item, dict):
            raise ClaudeCodeAdapterError(f"session state field 'command_results[{index}]' must be an object: {path}")

        command = item.get("command")
        outcome = item.get("outcome")
        tool_use_id = item.get("tool_use_id")
        exit_code = item.get("exit_code")
        error = item.get("error")
        is_interrupt = item.get("is_interrupt")

        if not isinstance(command, str) or not command.strip():
            raise ClaudeCodeAdapterError(f"session state field 'command_results[{index}].command' must be a string: {path}")
        if outcome not in {"success", "failure"}:
            raise ClaudeCodeAdapterError(
                f"session state field 'command_results[{index}].outcome' must be 'success' or 'failure': {path}"
            )
        if tool_use_id is not None and not isinstance(tool_use_id, str):
            raise ClaudeCodeAdapterError(f"session state field 'command_results[{index}].tool_use_id' must be a string: {path}")
        if exit_code is not None and not isinstance(exit_code, int):
            raise ClaudeCodeAdapterError(f"session state field 'command_results[{index}].exit_code' must be an integer: {path}")
        if error is not None and not isinstance(error, str):
            raise ClaudeCodeAdapterError(f"session state field 'command_results[{index}].error' must be a string: {path}")
        if is_interrupt is not None and not isinstance(is_interrupt, bool):
            raise ClaudeCodeAdapterError(
                f"session state field 'command_results[{index}].is_interrupt' must be a boolean: {path}"
            )

        command_results.append(
            ClaudeCodeCommandResult(
                command=command.strip(),
                outcome=outcome,
                tool_use_id=tool_use_id.strip() if isinstance(tool_use_id, str) and tool_use_id.strip() else None,
                exit_code=exit_code,
                error=error.strip() if isinstance(error, str) and error.strip() else None,
                is_interrupt=is_interrupt,
            )
        )

    report_path = payload.get("report_path")
    if not isinstance(report_path, str) or not report_path.strip():
        raise ClaudeCodeAdapterError(f"session state field 'report_path' must be a string: {path}")

    return ClaudeCodeSessionState(
        repo_root=str(root),
        session_id=session_id,
        read_paths=_require_list("read_paths"),
        write_paths=_require_list("write_paths"),
        commands=_require_list("commands"),
        claims=_require_list("claims"),
        command_results=command_results,
        report_path=report_path,
    )


def initialize_session_state(repo_root: Path | str, session_id: str) -> ClaudeCodeSessionState:
    """Reset the current Claude Code session state for a repo."""

    root = _resolve_repo_root(repo_root)
    state = _write_state(_empty_state(root, session_id))
    active_path = _active_session_path(root)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(session_id + "\n", encoding="utf-8")
    return state


def ensure_session_state(repo_root: Path | str, session_id: str) -> ClaudeCodeSessionState:
    """Return a session state that is guaranteed to exist on disk."""

    root = _resolve_repo_root(repo_root)
    state_path = _session_state_path(root, session_id)
    active_session_id = resolve_active_session_id(root)
    if state_path.exists() and active_session_id == session_id:
        return load_session_state(root, session_id)

    state = _write_state(load_session_state(root, session_id))
    active_path = _active_session_path(root)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(session_id + "\n", encoding="utf-8")
    return state


def cleanup_session_state(repo_root: Path | str, session_id: str) -> None:
    """Delete one session's mutable state while keeping the latest report."""

    root = _resolve_repo_root(repo_root)
    state_path = _session_state_path(root, session_id)
    if state_path.exists():
        state_path.unlink()

    active_path = _active_session_path(root)
    if active_path.exists() and active_path.read_text(encoding="utf-8").strip() == session_id:
        active_path.unlink()


def resolve_active_session_id(repo_root: Path | str) -> str | None:
    """Return the active Claude Code session id for a repo, if known."""

    root = _resolve_repo_root(repo_root)
    active_path = _active_session_path(root)
    if not active_path.exists():
        return None
    session_id = active_path.read_text(encoding="utf-8").strip()
    return session_id or None


def resolve_session_report_path(repo_root: Path | str, session_id: str | None = None) -> Path:
    """Resolve the saved report path for one Claude Code session."""

    root = _resolve_repo_root(repo_root)

    if session_id:
        report_path = _session_report_path(root, session_id)
        if not report_path.exists():
            raise FileNotFoundError(f"no saved Claude Code hook report found for session {session_id!r}")
        return report_path

    active_session_id = resolve_active_session_id(root)
    if active_session_id:
        active_report = _session_report_path(root, active_session_id)
        if active_report.exists():
            return active_report

    reports_dir = _reports_dir(root)
    if not reports_dir.exists():
        raise FileNotFoundError("no saved Claude Code hook reports exist for this repo yet")

    report_candidates = sorted(
        (path for path in reports_dir.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not report_candidates:
        raise FileNotFoundError("no saved Claude Code hook reports exist for this repo yet")
    return report_candidates[0]


def _append_unique(values: list[str], item: str | None) -> list[str]:
    if item is None:
        return list(values)
    cleaned = item.strip()
    if not cleaned or cleaned in values:
        return list(values)
    return [*values, cleaned]


def _write_latest_report(repo_root: Path, session_id: str, report: CheckReport) -> str:
    report_path = _session_report_path(repo_root, session_id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(report_path)


def _read_hook_payload(payload_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeAdapterError(f"hook payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaudeCodeAdapterError("hook payload must be a JSON object")
    return payload


def _require_session_id(payload: dict[str, Any]) -> str:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ClaudeCodeAdapterError("hook payload must include a non-empty string 'session_id'")
    return session_id.strip()


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    if tool_input is None:
        return {}
    if not isinstance(tool_input, dict):
        raise ClaudeCodeAdapterError("hook payload field 'tool_input' must be a JSON object when present")
    return tool_input


def _file_path_from_tool_input(tool_input: dict[str, Any]) -> str | None:
    value = tool_input.get("file_path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _command_from_tool_input(tool_input: dict[str, Any]) -> str | None:
    value = tool_input.get("command")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _tool_use_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("tool_use_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_response")
    if isinstance(value, dict):
        return value
    return {}


def _extract_exit_code(payload: dict[str, Any]) -> int | None:
    tool_response = _tool_response(payload)
    for key in ("exit_code", "exitCode", "status_code", "statusCode"):
        value = tool_response.get(key)
        if isinstance(value, int):
            return value
    return None


def _command_result_from_payload(payload: dict[str, Any], *, outcome: str) -> ClaudeCodeCommandResult | None:
    if payload.get("tool_name") not in COMMAND_TOOL_NAMES:
        return None
    command = _command_from_tool_input(_tool_input(payload))
    if command is None:
        return None
    error = payload.get("error")
    is_interrupt = payload.get("is_interrupt")
    return ClaudeCodeCommandResult(
        command=command,
        outcome=outcome,
        tool_use_id=_tool_use_id(payload),
        exit_code=_extract_exit_code(payload),
        error=error.strip() if isinstance(error, str) and error.strip() else None,
        is_interrupt=is_interrupt if isinstance(is_interrupt, bool) else None,
    )


def _append_command_result(
    results: list[ClaudeCodeCommandResult],
    result: ClaudeCodeCommandResult | None,
) -> list[ClaudeCodeCommandResult]:
    if result is None:
        return list(results)
    return [*results, result]


def _record_tool_use(state: ClaudeCodeSessionState, payload: dict[str, Any]) -> ClaudeCodeSessionState:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return state

    tool_input = _tool_input(payload)
    if tool_name in READ_TOOL_NAMES:
        return ClaudeCodeSessionState(
            repo_root=state.repo_root,
            session_id=state.session_id,
            read_paths=_append_unique(state.read_paths, _file_path_from_tool_input(tool_input)),
            write_paths=list(state.write_paths),
            commands=list(state.commands),
            claims=list(state.claims),
            command_results=list(state.command_results),
            report_path=state.report_path,
        )
    if tool_name in WRITE_TOOL_NAMES:
        return ClaudeCodeSessionState(
            repo_root=state.repo_root,
            session_id=state.session_id,
            read_paths=list(state.read_paths),
            write_paths=_append_unique(state.write_paths, _file_path_from_tool_input(tool_input)),
            commands=list(state.commands),
            claims=list(state.claims),
            command_results=list(state.command_results),
            report_path=state.report_path,
        )
    if tool_name in COMMAND_TOOL_NAMES:
        command_result = _command_result_from_payload(payload, outcome="success")
        return ClaudeCodeSessionState(
            repo_root=state.repo_root,
            session_id=state.session_id,
            read_paths=list(state.read_paths),
            write_paths=list(state.write_paths),
            commands=_append_unique(state.commands, _command_from_tool_input(tool_input)),
            claims=list(state.claims),
            command_results=_append_command_result(state.command_results, command_result),
            report_path=state.report_path,
        )
    return state


def _record_tool_failure(state: ClaudeCodeSessionState, payload: dict[str, Any]) -> ClaudeCodeSessionState:
    command_result = _command_result_from_payload(payload, outcome="failure")
    if command_result is None:
        return state
    return ClaudeCodeSessionState(
        repo_root=state.repo_root,
        session_id=state.session_id,
        read_paths=list(state.read_paths),
        write_paths=list(state.write_paths),
        commands=list(state.commands),
        claims=list(state.claims),
        command_results=_append_command_result(state.command_results, command_result),
        report_path=state.report_path,
    )


def _run_check(
    repo_root: Path,
    session_id: str,
    *,
    read_paths: list[str],
    write_paths: list[str],
    commands: list[str],
    claims: list[str],
) -> CheckReport:
    report = check_repo_policy(
        repo_root,
        read_paths=read_paths,
        write_paths=write_paths,
        commands=commands,
        claims=claims,
    )
    _write_latest_report(repo_root, session_id, report)
    return report


def _first_lines_for_violations(violations: list[Violation], *, title: str) -> str:
    lines = [title]
    for violation in violations[:3]:
        lines.append(f"- [{violation.rule_id}] {violation.recommended_action}")
    if len(violations) > 3:
        lines.append(f"- {len(violations) - 3} more violation(s) remain.")
    return "\n".join(lines)


def _pre_write_blocking_violations(report: CheckReport) -> list[Violation]:
    return [
        violation
        for violation in report.violations
        if violation.mode in BLOCKING_MODES and violation.kind in PRE_WRITE_BLOCK_KINDS
    ]


def _blocking_violations(report: CheckReport) -> list[Violation]:
    return [violation for violation in report.violations if violation.mode in BLOCKING_MODES]


def _post_tool_feedback(report: CheckReport) -> str | None:
    if report.decision == "pass":
        return None

    title = "cldc: workflow warnings remain after this tool call."
    if report.decision == "block":
        title = "cldc: blocking workflow requirements still remain before Claude can finish."
    return _first_lines_for_violations(report.violations, title=title)


def _post_tool_json_output(report: CheckReport) -> str | None:
    message = _post_tool_feedback(report)
    if message is None:
        return None

    payload: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }
    if report.decision == "block":
        payload["decision"] = "block"
        payload["reason"] = message
    return json.dumps(payload, sort_keys=True)


def _post_tool_failure_json_output(state: ClaudeCodeSessionState) -> str | None:
    if not state.command_results:
        return None

    latest = state.command_results[-1]
    if latest.outcome != "failure":
        return None

    lines = [f"cldc recorded failed command `{latest.command}`."]
    if latest.error:
        lines.append(latest.error)
    lines.append("Only successful commands count toward `require_command` rules.")
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": "\n".join(lines),
            }
        },
        sort_keys=True,
    )


def _stop_block_payload(report: CheckReport) -> dict[str, str]:
    violations = _blocking_violations(report)
    reason = _first_lines_for_violations(
        violations,
        title="cldc: blocking workflow requirements still remain before this session can stop.",
    )
    return {"decision": "block", "reason": reason}


def record_claude_claim(
    repo_root: Path | str,
    claim: str,
    *,
    session_id: str | None = None,
) -> ClaudeCodeClaimReport:
    """Append one explicit claim to the active Claude Code session."""

    root = _resolve_repo_root(repo_root)
    cleaned_claim = claim.strip()
    if not cleaned_claim:
        raise ClaudeCodeAdapterError("claim must be a non-empty string")

    resolved_session_id = session_id or resolve_active_session_id(root)
    if not resolved_session_id:
        raise ClaudeCodeAdapterError("no active Claude Code session found for this repo; pass --session to target one explicitly")

    state = load_session_state(root, resolved_session_id)
    updated = ClaudeCodeSessionState(
        repo_root=state.repo_root,
        session_id=state.session_id,
        read_paths=list(state.read_paths),
        write_paths=list(state.write_paths),
        commands=list(state.commands),
        claims=_append_unique(state.claims, cleaned_claim),
        command_results=list(state.command_results),
        report_path=state.report_path,
    )
    persisted = _write_state(updated)
    _run_check(
        root,
        resolved_session_id,
        read_paths=persisted.read_paths,
        write_paths=persisted.write_paths,
        commands=persisted.commands,
        claims=persisted.claims,
    )
    return ClaudeCodeClaimReport(
        repo_root=str(root),
        session_id=resolved_session_id,
        claim=cleaned_claim,
        claim_count=len(updated.claims),
        state_path=str(_session_state_path(root, resolved_session_id)),
        report_path=updated.report_path,
    )


def run_session_start(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Initialize one Claude Code hook session."""

    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    initialize_session_state(repo_root, session_id)
    return HookRuntimeResult(exit_code=0)


def run_pre_tool_use(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Block write-time preconditions before Claude modifies a file."""

    root = _resolve_repo_root(repo_root)
    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    state = ensure_session_state(root, session_id)

    tool_name = payload.get("tool_name")
    if tool_name not in WRITE_TOOL_NAMES:
        return HookRuntimeResult(exit_code=0)

    pending_write = _file_path_from_tool_input(_tool_input(payload))
    if pending_write is None:
        return HookRuntimeResult(exit_code=0)

    report = _run_check(
        root,
        session_id,
        read_paths=state.read_paths,
        write_paths=[*state.write_paths, pending_write],
        commands=state.commands,
        claims=state.claims,
    )
    violations = _pre_write_blocking_violations(report)
    if not violations:
        return HookRuntimeResult(exit_code=0)

    return HookRuntimeResult(
        exit_code=2,
        stderr=_first_lines_for_violations(
            violations,
            title="cldc blocked this file modification before execution.",
        ),
    )


def run_post_tool_use(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Record successful tool evidence and surface JSON hook feedback."""

    root = _resolve_repo_root(repo_root)
    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    state = ensure_session_state(root, session_id)
    updated = _write_state(_record_tool_use(state, payload))

    tool_name = payload.get("tool_name")
    if tool_name not in READ_TOOL_NAMES | WRITE_TOOL_NAMES | COMMAND_TOOL_NAMES:
        return HookRuntimeResult(exit_code=0)

    report = _run_check(
        root,
        session_id,
        read_paths=updated.read_paths,
        write_paths=updated.write_paths,
        commands=updated.commands,
        claims=updated.claims,
    )
    if tool_name in READ_TOOL_NAMES:
        return HookRuntimeResult(exit_code=0)
    return HookRuntimeResult(exit_code=0, stdout=_post_tool_json_output(report))


def run_post_tool_use_failure(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Record failed tool executions and keep the saved report fresh."""

    root = _resolve_repo_root(repo_root)
    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    state = ensure_session_state(root, session_id)
    updated = _write_state(_record_tool_failure(state, payload))

    _run_check(
        root,
        session_id,
        read_paths=updated.read_paths,
        write_paths=updated.write_paths,
        commands=updated.commands,
        claims=updated.claims,
    )
    return HookRuntimeResult(exit_code=0, stdout=_post_tool_failure_json_output(updated))


def run_stop(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Block session completion while blocking workflow invariants remain."""

    root = _resolve_repo_root(repo_root)
    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    state = ensure_session_state(root, session_id)
    report = _run_check(
        root,
        session_id,
        read_paths=state.read_paths,
        write_paths=state.write_paths,
        commands=state.commands,
        claims=state.claims,
    )
    if not _blocking_violations(report):
        return HookRuntimeResult(exit_code=0)

    # Avoid endless loops when Claude is already continuing because of this hook.
    if payload.get("stop_hook_active") is True:
        return HookRuntimeResult(exit_code=0)

    return HookRuntimeResult(
        exit_code=0,
        stdout=json.dumps(_stop_block_payload(report), sort_keys=True),
    )


def run_session_end(repo_root: Path | str, payload_text: str) -> HookRuntimeResult:
    """Clean up the mutable portion of one Claude Code session."""

    payload = _read_hook_payload(payload_text)
    session_id = _require_session_id(payload)
    cleanup_session_state(repo_root, session_id)
    return HookRuntimeResult(exit_code=0)
