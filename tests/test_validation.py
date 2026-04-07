import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents


def test_loader_discovers_policy_files_without_include_config(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# ok\n")
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "base.yml").write_text(
        "rules:\n  - id: implicit\n    kind: deny_write\n    paths: ['generated/**']\n    message: implicit\n"
    )

    bundle = load_policy_sources(tmp_path)

    assert [source.kind for source in bundle.sources] == ["claude_md", "policy_file"]
    assert bundle.sources[1].path == "policies/base.yml"


def test_parser_rejects_invalid_default_mode(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# ok\n")
    (tmp_path / ".claude-compiler.yaml").write_text("default_mode: chaos\n")

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="default_mode"):
        parse_rule_documents(bundle)


def test_parser_rejects_unknown_rule_kind(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("```cldc\nrules:\n  - id: weird\n    kind: nonsense\n    message: nope\n```\n")

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="unknown rule kind"):
        parse_rule_documents(bundle)


def test_loader_rejects_include_patterns_that_escape_repo_root(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# ok\n")
    (tmp_path / ".claude-compiler.yaml").write_text("include:\n  - ../outside.yml\n")

    with pytest.raises(ValueError, match="stay within the repo root"):
        load_policy_sources(tmp_path)


def test_cli_returns_nonzero_and_actionable_error_on_bad_input(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("```cldc\nrules:\n  - id: broken\n    message: missing kind\n```\n")

    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "compile", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 1
    assert "compile failed" in result.stderr.lower()


def test_cli_returns_json_error_payload_on_bad_input(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("```cldc\nrules:\n  - id: broken\n    message: missing kind\n```\n")

    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "compile", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload == {
        "command": "compile",
        "error": "rule 'broken' kind is required",
        "ok": False,
    }


def test_compiler_emits_lockfile_schema_version(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )

    compiled = compile_repo_policy(tmp_path)
    payload = json.loads((tmp_path / ".claude" / "policy.lock.json").read_text())

    assert compiled.format_version == "1"
    assert payload["$schema"] == "https://cldc.dev/schemas/policy-lock/v1"
    assert compiled.source_digest == payload["source_digest"]


def test_doctor_flags_stale_lockfile(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    claude_path = tmp_path / "CLAUDE.md"
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: changed\n```\n"
    )
    lockfile_mtime = (tmp_path / ".claude" / "policy.lock.json").stat().st_mtime
    os.utime(claude_path, (lockfile_mtime + 5, lockfile_mtime + 5))

    report = doctor_repo_policy(tmp_path)

    assert report.errors == []
    assert report.source_digest is not None
    assert report.lockfile_source_digest is not None
    assert any("stale" in warning or "source_digest" in warning for warning in report.warnings)
    assert report.next_action == "Re-run `cldc compile` to refresh the lockfile, then commit the updated artifact."


def test_doctor_reports_lockfile_schema_drift(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    payload = json.loads(lockfile.read_text())
    payload["$schema"] = "https://cldc.dev/schemas/policy-lock/v0"
    payload["format_version"] = "0"
    payload["rule_count"] = 999
    lockfile.write_text(json.dumps(payload))

    report = doctor_repo_policy(tmp_path)

    assert report.errors == []
    assert report.lockfile_schema == "https://cldc.dev/schemas/policy-lock/v0"
    assert report.lockfile_format_version == "0"
    assert report.lockfile_source_digest is not None
    assert any("schema does not match" in warning for warning in report.warnings)
    assert any("format_version does not match" in warning for warning in report.warnings)
    assert any("rule_count does not match" in warning for warning in report.warnings)
    assert report.next_action == "Re-run `cldc compile` to refresh the lockfile, then commit the updated artifact."


def test_doctor_reports_content_drift_even_when_mtime_and_rule_count_match(tmp_path):
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n")
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    lockfile_mtime = lockfile.stat().st_mtime

    claude_path.write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: changed without touching rule count\n```\n"
    )
    os.utime(claude_path, (lockfile_mtime - 5, lockfile_mtime - 5))

    report = doctor_repo_policy(tmp_path)

    assert report.errors == []
    assert report.source_digest is not None
    assert report.lockfile_source_digest is not None
    assert any("source_digest does not match" in warning for warning in report.warnings)
    assert report.next_action == "Re-run `cldc compile` to refresh the lockfile, then commit the updated artifact."


def test_doctor_reports_malformed_lockfile_json(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    lockfile.write_text("{not json}\n")

    report = doctor_repo_policy(tmp_path)

    assert any("not valid JSON" in error for error in report.errors)
    assert report.next_action == "Fix the reported policy or lockfile errors, then rerun `cldc doctor` and `cldc compile`."
