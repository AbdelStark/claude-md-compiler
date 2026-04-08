"""Tests for the stateful Claude Code hook adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.claude_code_adapter import (
    ensure_session_state,
    load_session_state,
    record_claude_claim,
    resolve_session_report_path,
    run_post_tool_use,
    run_post_tool_use_failure,
    run_pre_tool_use,
    run_session_end,
    run_session_start,
    run_stop,
)


def _payload(*, session_id: str, tool_name: str | None = None, tool_input: dict[str, object] | None = None, **extra: object) -> str:
    payload: dict[str, object] = {
        "session_id": session_id,
        "transcript_path": "/tmp/transcript.jsonl",
    }
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if tool_input is not None:
        payload["tool_input"] = tool_input
    payload.update(extra)
    return json.dumps(payload)


def _write_require_read_block_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text("# repo\n", encoding="utf-8")
    (tmp_path / ".claude-compiler.yaml").write_text(
        "rules:\n"
        "  - id: read-architecture-first\n"
        "    kind: require_read\n"
        "    mode: block\n"
        "    paths: ['src/**']\n"
        "    before_paths: ['docs/rfcs/**']\n"
        "    message: Read the architecture docs first.\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)
    return tmp_path


def _write_require_claim_block_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed']\n"
        "    message: QA must sign off before finishing source edits.\n"
        "```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)
    return tmp_path


def _write_require_command_success_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: tests-pass\n"
        "    kind: require_command_success\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    commands: ['pytest -q']\n"
        "    message: Tests must pass before source changes are done.\n"
        "```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)
    return tmp_path


def test_pre_tool_use_blocks_missing_blocking_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _write_require_read_block_repo(tmp_path / "repo")
    session_id = "session-pre-read"
    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))

    assert run_session_start(repo, _payload(session_id=session_id)).exit_code == 0

    blocked = run_pre_tool_use(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Write",
            tool_input={"file_path": "src/app.py", "content": "print('hi')"},
        ),
    )
    assert blocked.exit_code == 2
    assert blocked.stderr is not None
    assert "read-architecture-first" in blocked.stderr

    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Read",
                tool_input={"file_path": "docs/rfcs/0001.md"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )

    allowed = run_pre_tool_use(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Write",
            tool_input={"file_path": "src/app.py", "content": "print('hi')"},
        ),
    )
    assert allowed.exit_code == 0
    assert allowed.stderr is None


def test_stop_blocks_until_required_claim_is_recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _write_require_claim_block_repo(tmp_path / "repo")
    session_id = "session-claim"
    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))

    assert run_session_start(repo, _payload(session_id=session_id)).exit_code == 0
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Write",
                tool_input={"file_path": "src/app.py", "content": "print('hi')"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )

    blocked = run_stop(
        repo,
        _payload(
            session_id=session_id,
            stop_hook_active=False,
            last_assistant_message="Done.",
        ),
    )
    assert blocked.exit_code == 0
    assert blocked.stdout is not None
    stop_payload = json.loads(blocked.stdout)
    assert stop_payload["decision"] == "block"
    assert "qa-sign-off" in stop_payload["reason"]

    claim_report = record_claude_claim(repo, "qa-reviewed")
    assert claim_report.session_id == session_id
    assert claim_report.claim_count == 1
    updated_report = json.loads(Path(claim_report.report_path).read_text(encoding="utf-8"))
    assert updated_report["decision"] == "pass"

    unblocked = run_stop(
        repo,
        _payload(
            session_id=session_id,
            stop_hook_active=False,
            last_assistant_message="Done.",
        ),
    )
    assert unblocked.exit_code == 0
    assert unblocked.stdout is None


def test_post_tool_use_records_session_evidence_and_latest_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "repo_a"
    repo = tmp_path / "repo"
    repo.mkdir()
    for source in fixture.rglob("*"):
        if source.is_file():
            destination = repo / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    compile_repo_policy(repo)

    session_id = "session-state"
    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))
    assert run_session_start(repo, _payload(session_id=session_id)).exit_code == 0

    post_write = run_post_tool_use(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Write",
            tool_input={"file_path": "src/main.py", "content": "print('hi')"},
            tool_response={"success": True},
        ),
    )
    assert post_write.exit_code == 0
    assert post_write.stdout is not None
    post_write_payload = json.loads(post_write.stdout)
    assert post_write_payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "run-tests" in post_write_payload["hookSpecificOutput"]["additionalContext"]

    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Bash",
                tool_input={"command": "pytest -q"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Read",
                tool_input={"file_path": "docs/rfcs/CLDC-0006-validator-engine.md"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )

    state = ensure_session_state(repo, session_id)
    assert state.write_paths == ["src/main.py"]
    assert state.commands == ["pytest -q"]
    assert state.read_paths == ["docs/rfcs/CLDC-0006-validator-engine.md"]
    assert [result.outcome for result in state.command_results] == ["success"]
    assert Path(state.report_path).exists()

    final_stop = run_stop(
        repo,
        _payload(
            session_id=session_id,
            stop_hook_active=False,
            last_assistant_message="Done.",
        ),
    )
    assert final_stop.exit_code == 0
    assert final_stop.stdout is None

    persisted = load_session_state(repo, session_id)
    assert persisted.commands == ["pytest -q"]


def test_adapter_require_command_success_distinguishes_failed_and_successful_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _write_require_command_success_repo(tmp_path / "repo")
    session_id = "session-command-success"
    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))

    assert run_session_start(repo, _payload(session_id=session_id)).exit_code == 0
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Write",
                tool_input={"file_path": "src/app.py", "content": "print('hi')"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )

    failed = run_post_tool_use_failure(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            error="Command exited with non-zero status code 1",
        ),
    )
    assert failed.exit_code == 0
    blocked = run_stop(
        repo,
        _payload(
            session_id=session_id,
            stop_hook_active=False,
            last_assistant_message="Done.",
        ),
    )
    assert blocked.stdout is not None
    blocked_payload = json.loads(blocked.stdout)
    assert blocked_payload["decision"] == "block"
    assert "tests-pass" in blocked_payload["reason"]

    successful = run_post_tool_use(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            tool_response={"success": True},
        ),
    )
    assert successful.exit_code == 0
    unblocked = run_stop(
        repo,
        _payload(
            session_id=session_id,
            stop_hook_active=False,
            last_assistant_message="Done.",
        ),
    )
    assert unblocked.stdout is None


def test_post_tool_use_failure_records_failed_command_and_latest_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "repo_a"
    repo = tmp_path / "repo"
    repo.mkdir()
    for source in fixture.rglob("*"):
        if source.is_file():
            destination = repo / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    compile_repo_policy(repo)

    session_id = "session-failure"
    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))
    assert run_session_start(repo, _payload(session_id=session_id)).exit_code == 0
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id=session_id,
                tool_name="Write",
                tool_input={"file_path": "src/main.py", "content": "print('hi')"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )

    failed = run_post_tool_use_failure(
        repo,
        _payload(
            session_id=session_id,
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            tool_use_id="toolu_123",
            error="Command exited with non-zero status code 1",
            is_interrupt=False,
        ),
    )
    assert failed.exit_code == 0
    assert failed.stdout is not None
    failure_payload = json.loads(failed.stdout)
    assert failure_payload["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"
    assert "failed command `pytest -q`" in failure_payload["hookSpecificOutput"]["additionalContext"]

    state = load_session_state(repo, session_id)
    assert state.commands == []
    assert len(state.command_results) == 1
    assert state.command_results[0].outcome == "failure"
    assert state.command_results[0].tool_use_id == "toolu_123"
    assert state.command_results[0].error == "Command exited with non-zero status code 1"

    latest_report = json.loads(Path(state.report_path).read_text(encoding="utf-8"))
    assert latest_report["decision"] == "warn"
    assert latest_report["violations"][0]["rule_id"] == "must-read-rfc"


def test_resolve_session_report_path_falls_back_to_latest_saved_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "repo_a"
    repo = tmp_path / "repo"
    repo.mkdir()
    for source in fixture.rglob("*"):
        if source.is_file():
            destination = repo / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    compile_repo_policy(repo)

    monkeypatch.setenv("CLDC_CLAUDE_STATE_DIR", str(tmp_path / "adapter-state"))

    assert run_session_start(repo, _payload(session_id="session-a")).exit_code == 0
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id="session-a",
                tool_name="Write",
                tool_input={"file_path": "src/main.py", "content": "print('a')"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )
    report_a = resolve_session_report_path(repo, session_id="session-a")

    assert run_session_start(repo, _payload(session_id="session-b")).exit_code == 0
    assert (
        run_post_tool_use(
            repo,
            _payload(
                session_id="session-b",
                tool_name="Write",
                tool_input={"file_path": "src/main.py", "content": "print('b')"},
                tool_response={"success": True},
            ),
        ).exit_code
        == 0
    )
    assert run_session_end(repo, _payload(session_id="session-b")).exit_code == 0
    latest_report = resolve_session_report_path(repo)

    assert latest_report != report_a
    assert latest_report.name == "session-b.json"
