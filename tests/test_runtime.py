import json
import os
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.events import CommandResult, load_execution_inputs
from cldc.runtime.git import collect_git_write_paths
from cldc.runtime.remediation import FIX_PLAN_FORMAT_VERSION, FIX_PLAN_SCHEMA, build_fix_plan, render_fix_plan
from cldc.runtime.report_schema import CHECK_REPORT_FORMAT_VERSION, CHECK_REPORT_SCHEMA


@pytest.fixture
def compiled_repo(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "repo_a"
    target = tmp_path / "repo"
    target.mkdir()

    for source in fixture.rglob("*"):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    compile_repo_policy(target)
    return target


def test_check_repo_policy_reports_warn_only_violations(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=["src/main.py"],
    )

    assert report.ok is True
    assert report.decision == "warn"
    assert report.violation_count == 2
    assert report.blocking_violation_count == 0
    assert report.summary == "Policy check found 2 non-blocking violation(s)."
    assert report.next_action == "Read at least one path matching docs/rfcs/** before modifying src/main.py."
    assert [violation.rule_id for violation in report.violations] == ["must-read-rfc", "run-tests"]
    require_read = report.violations[0]
    assert require_read.required_paths == ["docs/rfcs/**"]
    assert (
        require_read.explanation
        == "Write activity src/main.py triggered require_read rule 'must-read-rfc', but no required read matched docs/rfcs/**."
    )
    require_command = report.violations[1]
    assert require_command.required_commands == ["pytest -q"]
    assert require_command.recommended_action == "Run one of the required commands before finishing: pytest -q."
    assert report.inputs["claims"] == []

    payload = report.to_dict()
    assert payload["$schema"] == CHECK_REPORT_SCHEMA
    assert payload["format_version"] == CHECK_REPORT_FORMAT_VERSION


def test_check_repo_policy_passes_when_required_inputs_are_present(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        read_paths=["docs/rfcs/CLDC-0006-validator-engine.md"],
        write_paths=["src/main.py"],
        commands=["pytest -q"],
    )

    assert report.ok is True
    assert report.decision == "pass"
    assert report.summary == "Policy check passed with no violations."
    assert report.next_action is None
    assert report.violations == []


def _write_require_command_success_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: test-pass-required\n"
        "    kind: require_command_success\n"
        "    when_paths: ['src/**']\n"
        "    commands: ['pytest -q']\n"
        "    message: Tests must pass before source changes are done.\n"
        "```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)


def test_check_repo_policy_enforces_require_command_success_with_failed_command_result(tmp_path):
    _write_require_command_success_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py"],
        command_results=[CommandResult(command="pytest -q", outcome="failure")],
    )

    assert report.decision == "warn"
    assert report.violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == "test-pass-required"
    assert violation.kind == "require_command_success"
    assert violation.required_commands == ["pytest -q"]
    assert violation.recommended_action == "Run one of the required commands successfully before finishing: pytest -q."
    assert report.inputs["commands"] == ["pytest -q"]


def test_check_repo_policy_passes_require_command_success_with_successful_command_result(tmp_path):
    _write_require_command_success_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py"],
        command_results=[CommandResult(command="pytest -q", outcome="success")],
    )

    assert report.decision == "pass"
    assert report.violations == []


def test_build_fix_plan_for_require_command_success_suggests_commands(tmp_path):
    _write_require_command_success_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py"],
        command_results=[CommandResult(command="pytest -q", outcome="failure")],
    )
    plan = build_fix_plan(report.to_dict())

    assert plan["decision"] == "warn"
    assert plan["remediation_count"] == 1
    remediation = plan["remediations"][0]
    assert remediation["kind"] == "require_command_success"
    assert remediation["suggested_commands"] == ["pytest -q"]
    assert "successfully" in remediation["steps"][0]


def test_check_repo_policy_merges_generic_and_outcome_aware_command_evidence(tmp_path):
    _write_require_command_success_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py"],
        commands=["ruff check ."],
        event_payload={
            "events": [
                {"kind": "command", "command": "pytest -q", "outcome": "success"},
            ]
        },
    )

    assert report.decision == "pass"
    assert report.inputs["commands"] == ["ruff check .", "pytest -q"]


def test_build_fix_plan_emits_versioned_remediations_for_violations(compiled_repo):
    report = check_repo_policy(compiled_repo, write_paths=["src/main.py"])

    plan = build_fix_plan(report.to_dict())

    assert plan["$schema"] == FIX_PLAN_SCHEMA
    assert plan["format_version"] == FIX_PLAN_FORMAT_VERSION
    assert plan["decision"] == "warn"
    assert plan["violation_count"] == 2
    assert plan["remediation_count"] == 2
    assert plan["summary"] == "Generated 2 remediation plan item(s) for 2 violation(s) in a `warn` policy report."
    assert plan["next_action"] == ("Read at least one required context path before keeping changes to src/main.py: docs/rfcs/**.")
    first = plan["remediations"][0]
    assert first["rule_id"] == "must-read-rfc"
    assert first["priority"] == "non-blocking"
    assert first["files_to_inspect"] == [".claude-compiler.yaml", "src/main.py", "docs/rfcs/**"]
    assert first["suggested_commands"] == []
    second = plan["remediations"][1]
    assert second["rule_id"] == "run-tests"
    assert second["suggested_commands"] == ["pytest -q"]
    assert second["can_autofix"] is False


def test_build_fix_plan_for_pass_report_has_no_remediations(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        read_paths=["docs/rfcs/CLDC-0006-validator-engine.md"],
        write_paths=["src/main.py"],
        commands=["pytest -q"],
    )

    plan = build_fix_plan(report.to_dict())

    assert plan["format_version"] == FIX_PLAN_FORMAT_VERSION
    assert plan["decision"] == "pass"
    assert plan["remediation_count"] == 0
    assert plan["remediations"] == []
    assert plan["next_action"] is None
    assert plan["summary"] == "No remediation is required because the policy report has no violations."


def test_render_fix_plan_accepts_already_versioned_payload(compiled_repo):
    report = check_repo_policy(compiled_repo, write_paths=["generated/output.json"])
    plan = build_fix_plan(report.to_dict())

    rendered = render_fix_plan(plan, format="text")

    assert "Policy fix plan: block" in rendered
    assert "Suggested commands" not in rendered
    assert "generated-lock" in rendered


def test_load_execution_inputs_supports_batch_events_and_claims():
    payload = {
        "events": [
            {"kind": "read", "path": "docs/rfcs/CLDC-0006-validator-engine.md"},
            {"kind": "write", "path": "src/main.py"},
            {"kind": "command", "command": "pytest -q"},
            {"kind": "claim", "claim": "task-complete"},
        ]
    }

    inputs = load_execution_inputs(payload)

    assert inputs.read_paths == ["docs/rfcs/CLDC-0006-validator-engine.md"]
    assert inputs.write_paths == ["src/main.py"]
    assert inputs.commands == ["pytest -q"]
    assert inputs.claims == ["task-complete"]


def test_load_execution_inputs_rejects_malformed_event_payloads():
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_execution_inputs(["bad"])

    with pytest.raises(ValueError, match="events\\[0\\] must contain a string 'kind'"):
        load_execution_inputs({"events": [{}]})

    with pytest.raises(ValueError, match="events\\[0\\] kind 'write' requires a string 'path'"):
        load_execution_inputs({"events": [{"kind": "write"}]})


def test_check_repo_policy_normalizes_absolute_paths_inside_repo(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=[str((compiled_repo / "src/main.py").resolve())],
    )

    assert report.decision == "warn"
    assert [violation.rule_id for violation in report.violations] == ["must-read-rfc", "run-tests"]
    assert report.inputs["write_paths"] == ["src/main.py"]


def test_check_repo_policy_merges_explicit_inputs_with_event_payload(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        read_paths=["docs/rfcs/CLDC-0006-validator-engine.md"],
        event_payload={
            "events": [
                {"kind": "write", "path": "src/main.py"},
                {"kind": "command", "command": "pytest -q"},
                {"kind": "claim", "claim": "completed-runtime-check"},
            ]
        },
    )

    assert report.ok is True
    assert report.decision == "pass"
    assert report.inputs["claims"] == ["completed-runtime-check"]


def test_check_repo_policy_rejects_paths_outside_repo(compiled_repo, tmp_path):
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("nope\n")

    with pytest.raises(ValueError, match="outside the discovered repo root"):
        check_repo_policy(compiled_repo, write_paths=[str(outside.resolve())])


def test_check_repo_policy_blocks_deny_write_rule(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=["generated/output.json"],
    )

    assert report.ok is False
    assert report.decision == "block"
    assert report.summary == "Policy check found 1 violation(s), including 1 blocking violation(s)."
    assert report.next_action == "Avoid writing paths matching generated/**."
    assert report.blocking_violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == "generated-lock"
    assert violation.mode == "block"
    assert violation.explanation == "Write activity generated/output.json matched deny_write rule 'generated-lock'."
    assert violation.matched_paths == ["generated/output.json"]


def test_check_repo_policy_enforces_couple_change_rules(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: keep-tests-in-sync\n    kind: couple_change\n    paths: ['src/**']\n    when_paths: ['tests/**']\n    message: Update tests when source changes.\n```\n"
    )
    compile_repo_policy(tmp_path)

    report = check_repo_policy(tmp_path, write_paths=["src/app.py"])

    assert report.decision == "warn"
    assert report.summary == "Policy check found 1 non-blocking violation(s)."
    assert report.next_action == "Update at least one path matching tests/** alongside src/app.py."
    assert report.violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == "keep-tests-in-sync"
    assert violation.kind == "couple_change"
    assert violation.required_paths == ["tests/**"]
    assert violation.explanation == (
        "Write activity src/app.py triggered couple_change rule 'keep-tests-in-sync', but no coupled change matched tests/**."
    )


def test_check_repo_policy_passes_when_couple_change_has_companion_write(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: keep-tests-in-sync\n    kind: couple_change\n    paths: ['src/**']\n    when_paths: ['tests/**']\n    message: Update tests when source changes.\n```\n"
    )
    compile_repo_policy(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py", "tests/test_app.py"],
    )

    assert report.decision == "pass"
    assert report.violation_count == 0
    assert report.violations == []


def _write_require_claim_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed', 'security-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
    )
    compile_repo_policy(tmp_path)


def test_check_repo_policy_blocks_require_claim_when_no_claim_asserted(tmp_path):
    _write_require_claim_repo(tmp_path)

    report = check_repo_policy(tmp_path, write_paths=["src/app.py"])

    assert report.decision == "block"
    assert report.ok is False
    assert report.blocking_violation_count == 1
    assert report.violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == "qa-sign-off"
    assert violation.kind == "require_claim"
    assert violation.mode == "block"
    assert violation.required_claims == ["qa-reviewed", "security-reviewed"]
    assert violation.matched_claims == []
    assert violation.matched_paths == ["src/app.py"]
    assert violation.explanation == (
        "Write activity src/app.py triggered require_claim rule 'qa-sign-off', "
        "but no required claim matched qa-reviewed, security-reviewed."
    )
    assert violation.recommended_action == ("Record one of the required claims before finishing: qa-reviewed, security-reviewed.")

    serialized = violation.to_dict()
    assert serialized["matched_claims"] == []
    assert serialized["required_claims"] == ["qa-reviewed", "security-reviewed"]


def test_check_repo_policy_passes_require_claim_with_explicit_claim(tmp_path):
    _write_require_claim_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py"],
        claims=["qa-reviewed"],
    )

    assert report.decision == "pass"
    assert report.violation_count == 0
    assert report.violations == []
    assert report.inputs["claims"] == ["qa-reviewed"]


def test_check_repo_policy_passes_require_claim_via_event_payload(tmp_path):
    _write_require_claim_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        event_payload={
            "events": [
                {"kind": "write", "path": "src/app.py"},
                {"kind": "claim", "claim": "security-reviewed"},
            ]
        },
    )

    assert report.decision == "pass"
    assert report.inputs["claims"] == ["security-reviewed"]
    assert report.violations == []


def test_check_repo_policy_ignores_require_claim_when_scope_paths_not_touched(tmp_path):
    _write_require_claim_repo(tmp_path)

    # `docs/**` is outside the `when_paths: ['src/**']` scope, so the claim rule must not fire.
    report = check_repo_policy(tmp_path, write_paths=["docs/README.md"])

    assert report.decision == "pass"
    assert report.violations == []


def test_check_repo_policy_require_claim_emits_remediation_plan_with_suggested_claims(tmp_path):
    _write_require_claim_repo(tmp_path)
    report = check_repo_policy(tmp_path, write_paths=["src/app.py"])

    plan = build_fix_plan(report.to_dict())

    assert plan["remediation_count"] == 1
    remediation = plan["remediations"][0]
    assert remediation["rule_id"] == "qa-sign-off"
    assert remediation["kind"] == "require_claim"
    assert remediation["priority"] == "blocking"
    assert remediation["suggested_claims"] == ["qa-reviewed", "security-reviewed"]
    assert remediation["suggested_commands"] == []
    assert any("qa-reviewed" in step and "security-reviewed" in step for step in remediation["steps"])
    assert plan["next_action"] == (
        "Record at least one required claim before keeping changes to src/app.py: qa-reviewed, security-reviewed."
    )


def test_render_fix_plan_for_require_claim_includes_suggested_claims_line(tmp_path):
    _write_require_claim_repo(tmp_path)
    report = check_repo_policy(tmp_path, write_paths=["src/app.py"])
    plan = build_fix_plan(report.to_dict())

    rendered_text = render_fix_plan(plan, format="text")
    rendered_md = render_fix_plan(plan, format="markdown")

    assert "Suggested claims: qa-reviewed, security-reviewed" in rendered_text
    assert "**Suggested claims:** `qa-reviewed, security-reviewed`" in rendered_md


def test_check_repo_policy_rejects_unsupported_rule_kinds_in_lockfile(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    payload = json.loads(lockfile.read_text())
    payload["rules"][0]["kind"] = "unexpected_kind"
    lockfile.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="unsupported rule kind"):
        check_repo_policy(tmp_path, write_paths=["generated/output.json"])


def test_check_repo_policy_requires_existing_lockfile(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# repo\n")

    with pytest.raises(FileNotFoundError, match="cldc compile"):
        check_repo_policy(tmp_path)


def test_check_repo_policy_rejects_malformed_lockfile(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# repo\n")
    lock_dir = tmp_path / ".claude"
    lock_dir.mkdir()
    (lock_dir / "policy.lock.json").write_text("{not-json")

    with pytest.raises(ValueError, match="not valid JSON"):
        check_repo_policy(tmp_path)


def test_check_repo_policy_rejects_lockfile_schema_drift(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    payload = json.loads(lockfile.read_text())
    payload["$schema"] = "https://cldc.dev/schemas/policy-lock/v0"
    lockfile.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="schema does not match"):
        check_repo_policy(tmp_path, write_paths=["generated/output.json"])


def test_check_repo_policy_rejects_stale_lockfile(tmp_path):
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n")
    compile_repo_policy(tmp_path)
    lockfile_mtime = (tmp_path / ".claude" / "policy.lock.json").stat().st_mtime
    claude_path.write_text("```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: changed\n```\n")
    os.utime(claude_path, (lockfile_mtime + 5, lockfile_mtime + 5))

    with pytest.raises(ValueError, match=r"stale|source_digest"):
        check_repo_policy(tmp_path, write_paths=["generated/output.json"])


def _write_forbid_command_repo(tmp_path, *, scoped: bool = True):
    when_paths_line = "    when_paths: ['pyproject.toml']\n" if scoped else ""
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: no-raw-pip\n"
        "    kind: forbid_command\n"
        "    mode: block\n"
        f"{when_paths_line}"
        "    commands: ['pip install', 'pip install -r requirements.txt']\n"
        "    message: Use uv sync instead of pip install.\n"
        "```\n"
    )
    compile_repo_policy(tmp_path)


def test_check_repo_policy_blocks_forbid_command_when_scope_and_command_match(tmp_path):
    _write_forbid_command_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["pip install"],
    )

    assert report.decision == "block"
    assert report.ok is False
    assert report.blocking_violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == "no-raw-pip"
    assert violation.kind == "forbid_command"
    assert violation.mode == "block"
    assert violation.matched_commands == ["pip install"]
    assert violation.matched_paths == ["pyproject.toml"]
    assert "forbid_command rule 'no-raw-pip'" in violation.explanation
    assert "Do not run" in violation.recommended_action


def test_check_repo_policy_passes_forbid_command_when_command_not_run(tmp_path):
    _write_forbid_command_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["uv sync --locked"],
    )

    assert report.decision == "pass"
    assert report.violations == []


def test_check_repo_policy_passes_forbid_command_when_scope_not_touched(tmp_path):
    _write_forbid_command_repo(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["README.md"],
        commands=["pip install"],
    )

    assert report.decision == "pass"
    assert report.violations == []


def test_check_repo_policy_forbid_command_without_when_paths_is_repo_global(tmp_path):
    _write_forbid_command_repo(tmp_path, scoped=False)

    report = check_repo_policy(
        tmp_path,
        write_paths=["README.md"],
        commands=["pip install -r requirements.txt"],
    )

    assert report.decision == "block"
    assert len(report.violations) == 1
    assert report.violations[0].matched_commands == ["pip install -r requirements.txt"]
    # With no when_paths the rule does not need matched paths to fire.
    assert report.violations[0].matched_paths == []


def test_forbid_command_remediation_plan_includes_forbidden_commands(tmp_path):
    _write_forbid_command_repo(tmp_path)
    report = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["pip install"],
    )

    plan = build_fix_plan(report.to_dict())

    assert plan["remediation_count"] == 1
    remediation = plan["remediations"][0]
    assert remediation["kind"] == "forbid_command"
    assert remediation["priority"] == "blocking"
    assert remediation["forbidden_commands"] == ["pip install"]
    assert remediation["suggested_commands"] == []
    assert any("pip install" in step for step in remediation["steps"])


def test_render_fix_plan_for_forbid_command_includes_forbidden_commands_line(tmp_path):
    _write_forbid_command_repo(tmp_path)
    report = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["pip install"],
    )
    plan = build_fix_plan(report.to_dict())

    text = render_fix_plan(plan, format="text")
    md = render_fix_plan(plan, format="markdown")

    assert "Forbidden commands: pip install" in text
    assert "**Forbidden commands:** `pip install`" in md


def _init_git_repo(repo: Path) -> None:
    import subprocess

    # Local `commit.gpgsign=false` isolates the test repo from any
    # signing hooks configured in the developer or CI environment. Tests
    # must not depend on a signing key being present; otherwise the suite
    # cannot run in sandboxed or unattended environments.
    commands = [
        ["git", "init"],
        ["git", "config", "user.email", "cldc-tests@example.com"],
        ["git", "config", "user.name", "CLDC Tests"],
        ["git", "config", "commit.gpgsign", "false"],
        ["git", "config", "tag.gpgsign", "false"],
        ["git", "add", "."],
        ["git", "commit", "-m", "baseline"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr


def test_check_repo_policy_rejects_content_drift_even_when_mtime_and_rule_count_match(tmp_path):
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n")
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    lockfile_mtime = lockfile.stat().st_mtime

    claude_path.write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: changed without touching rule count\n```\n"
    )
    os.utime(claude_path, (lockfile_mtime - 5, lockfile_mtime - 5))

    with pytest.raises(ValueError, match="source_digest"):
        check_repo_policy(tmp_path, write_paths=["generated/output.json"])


def test_collect_git_write_paths_supports_staged_changes(compiled_repo):
    _init_git_repo(compiled_repo)
    (compiled_repo / "src").mkdir(exist_ok=True)
    (compiled_repo / "src" / "main.py").write_text('print("changed")\n')

    import subprocess

    stage_result = subprocess.run(
        ["git", "add", "src/main.py"],
        cwd=compiled_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stage_result.returncode == 0, stage_result.stderr

    write_paths, metadata = collect_git_write_paths(compiled_repo, staged=True)

    assert write_paths == ["src/main.py"]
    assert metadata["mode"] == "staged"
    assert metadata["git_command"] == ["git", "diff", "--cached", "--name-only"]


def test_collect_git_write_paths_supports_base_head_diff(compiled_repo):
    _init_git_repo(compiled_repo)

    import subprocess

    base_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=compiled_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert base_result.returncode == 0, base_result.stderr
    base_sha = base_result.stdout.strip()

    generated = compiled_repo / "generated" / "output.json"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text('{"status": "changed"}\n')
    add_result = subprocess.run(
        ["git", "add", "generated/output.json"],
        cwd=compiled_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert add_result.returncode == 0, add_result.stderr
    commit_result = subprocess.run(
        ["git", "commit", "-m", "touch generated output"],
        cwd=compiled_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert commit_result.returncode == 0, commit_result.stderr

    write_paths, metadata = collect_git_write_paths(compiled_repo, base=base_sha, head="HEAD")

    assert write_paths == ["generated/output.json"]
    assert metadata["mode"] == "range"
    assert metadata["base"] == base_sha
    assert metadata["head"] == "HEAD"


def test_collect_git_write_paths_requires_selection_mode(compiled_repo):
    _init_git_repo(compiled_repo)

    with pytest.raises(ValueError, match="requires either --staged or --base"):
        collect_git_write_paths(compiled_repo)
