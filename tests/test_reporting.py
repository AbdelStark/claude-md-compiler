"""Direct unit tests for ``cldc.runtime.reporting``.

The reporting module is a pure validator/renderer over JSON payloads
produced by ``cldc check``. These tests exercise the validation paths
and the text/markdown render branches without going through the CLI,
which lifts coverage of the file from ~28% to >=90%.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cldc.errors import ReportError
from cldc.runtime.report_schema import CHECK_REPORT_FORMAT_VERSION, CHECK_REPORT_SCHEMA
from cldc.runtime.reporting import (
    _normalize_git,
    _normalize_violation,
    load_check_report,
    load_check_report_file,
    load_check_report_text,
    render_check_report,
)


def _violation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "rule_id": "deny-generated",
        "kind": "deny_write",
        "mode": "block",
        "message": "no generated writes",
        "explanation": "writes to generated/** are denied",
        "recommended_action": "remove the offending write",
        "matched_paths": ["generated/foo.py"],
        "matched_commands": [],
        "matched_claims": [],
        "required_paths": [],
        "required_commands": [],
        "required_claims": [],
        "source_path": "CLAUDE.md",
        "source_block_id": "block-1",
    }
    base.update(overrides)
    return base


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "$schema": CHECK_REPORT_SCHEMA,
        "format_version": CHECK_REPORT_FORMAT_VERSION,
        "ok": False,
        "repo_root": "/repo",
        "lockfile_path": "/repo/.claude/policy.lock.json",
        "decision": "block",
        "default_mode": "warn",
        "summary": "1 violation",
        "next_action": "fix the write",
        "inputs": {
            "read_paths": ["src/main.py"],
            "write_paths": ["generated/foo.py"],
            "commands": ["pytest"],
            "claims": ["reviewed"],
        },
        "violation_count": 1,
        "blocking_violation_count": 1,
        "violations": [_violation()],
    }
    base.update(overrides)
    return base


class TestLoadCheckReport:
    def test_round_trips_minimal_payload(self):
        report = load_check_report(_payload(violations=[], violation_count=0, blocking_violation_count=0))
        assert report["decision"] == "block"
        assert report["$schema"] == CHECK_REPORT_SCHEMA
        assert report["format_version"] == CHECK_REPORT_FORMAT_VERSION
        assert report["violations"] == []

    def test_rejects_non_object_payload(self):
        with pytest.raises(ReportError, match="must be a JSON object"):
            load_check_report("not a dict")  # type: ignore[arg-type]

    def test_rejects_unknown_schema(self):
        with pytest.raises(ReportError, match=r"\$schema"):
            load_check_report(_payload(**{"$schema": "https://other/schema"}))

    def test_rejects_unknown_format_version(self):
        with pytest.raises(ReportError, match="format_version"):
            load_check_report(_payload(format_version="999"))

    def test_allows_missing_schema_and_format_version(self):
        payload = _payload()
        payload.pop("$schema")
        payload.pop("format_version")
        report = load_check_report(payload)
        assert report["$schema"] == CHECK_REPORT_SCHEMA
        assert report["format_version"] == CHECK_REPORT_FORMAT_VERSION

    def test_rejects_unknown_decision(self):
        with pytest.raises(ReportError, match="decision"):
            load_check_report(_payload(decision="explode"))

    def test_rejects_non_list_violations(self):
        with pytest.raises(ReportError, match="violations"):
            load_check_report(_payload(violations="oops"))

    def test_rejects_non_bool_ok(self):
        with pytest.raises(ReportError, match="'ok'"):
            load_check_report(_payload(ok="true"))

    def test_rejects_non_int_violation_count(self):
        with pytest.raises(ReportError, match="violation_count"):
            load_check_report(_payload(violation_count="1"))

    def test_rejects_empty_required_string(self):
        with pytest.raises(ReportError, match="repo_root"):
            load_check_report(_payload(repo_root=""))

    def test_rejects_non_dict_inputs(self):
        with pytest.raises(ReportError, match="inputs"):
            load_check_report(_payload(inputs="nope"))

    def test_rejects_non_string_in_input_list(self):
        bad = _payload()
        bad["inputs"]["read_paths"] = [123]
        with pytest.raises(ReportError, match=r"inputs\.read_paths\[0\]"):
            load_check_report(bad)

    def test_optional_next_action_can_be_none(self):
        report = load_check_report(_payload(next_action=None))
        assert report["next_action"] is None


class TestNormalizeGit:
    def test_returns_none_when_value_is_none(self):
        assert _normalize_git(None) is None

    def test_rejects_non_dict(self):
        with pytest.raises(ReportError, match="git"):
            _normalize_git("staged")

    def test_normalizes_staged_minimal(self):
        result = _normalize_git({"mode": "staged", "write_path_count": 3})
        assert result == {"mode": "staged", "write_path_count": 3}

    def test_includes_optional_base_head_and_command(self):
        result = _normalize_git(
            {
                "mode": "range",
                "write_path_count": 2,
                "base": "HEAD~1",
                "head": "HEAD",
                "git_command": ["git", "diff", "--name-only"],
            }
        )
        assert result == {
            "mode": "range",
            "write_path_count": 2,
            "base": "HEAD~1",
            "head": "HEAD",
            "git_command": ["git", "diff", "--name-only"],
        }

    def test_skips_none_optional_fields(self):
        result = _normalize_git({"mode": "staged", "write_path_count": 0, "base": None, "head": None})
        assert "base" not in result
        assert "head" not in result

    def test_rejects_bad_git_command_entries(self):
        with pytest.raises(ReportError, match="git.git_command"):
            _normalize_git({"mode": "staged", "write_path_count": 0, "git_command": [""]})

    def test_rejects_missing_mode(self):
        with pytest.raises(ReportError, match="git.mode"):
            _normalize_git({"write_path_count": 0})

    def test_rejects_non_int_write_path_count(self):
        with pytest.raises(ReportError, match="write_path_count"):
            _normalize_git({"mode": "staged", "write_path_count": "3"})


class TestNormalizeViolation:
    def test_rejects_non_dict(self):
        with pytest.raises(ReportError, match=r"violations\[0\]"):
            _normalize_violation("nope", index=0)

    @pytest.mark.parametrize(
        "field",
        ["rule_id", "kind", "mode", "message", "explanation", "recommended_action"],
    )
    def test_rejects_missing_required_string(self, field):
        violation = _violation()
        violation[field] = ""
        with pytest.raises(ReportError, match=field):
            _normalize_violation(violation, index=0)

    @pytest.mark.parametrize(
        "field",
        [
            "matched_paths",
            "matched_commands",
            "matched_claims",
            "required_paths",
            "required_commands",
            "required_claims",
        ],
    )
    def test_rejects_non_list_collections(self, field):
        violation = _violation()
        violation[field] = "x"
        with pytest.raises(ReportError, match=field):
            _normalize_violation(violation, index=0)

    def test_optional_provenance_fields_may_be_none(self):
        normalized = _normalize_violation(
            _violation(source_path=None, source_block_id=None),
            index=0,
        )
        assert normalized["source_path"] is None
        assert normalized["source_block_id"] is None


class TestRenderCheckReport:
    def test_text_render_includes_all_branches(self):
        payload = _payload()
        payload["git"] = {
            "mode": "range",
            "write_path_count": 4,
            "base": "main",
            "head": "HEAD",
        }
        violation = payload["violations"][0]
        violation["matched_commands"] = ["pytest"]
        violation["matched_claims"] = ["reviewed"]
        violation["required_paths"] = ["docs/CHANGELOG.md"]
        violation["required_commands"] = ["lint"]
        violation["required_claims"] = ["security-reviewed"]

        out = render_check_report(payload, format="text")
        assert "Policy explanation: block" in out
        assert "Git input: main...HEAD (4 changed paths)" in out
        assert "Recommended next action: fix the write" in out
        assert "1. [block] deny-generated (deny_write): no generated writes" in out
        assert "Why: writes to generated/** are denied" in out
        assert "Rule provenance: CLAUDE.md#block-1" in out
        assert "Matched paths: generated/foo.py" in out
        assert "Matched commands: pytest" in out
        assert "Matched claims: reviewed" in out
        assert "Required reads: docs/CHANGELOG.md" in out
        assert "Required commands: lint" in out
        assert "Required claims: security-reviewed" in out

    def test_text_render_staged_git_branch_and_no_violations(self):
        payload = _payload(
            violations=[],
            violation_count=0,
            blocking_violation_count=0,
            next_action=None,
        )
        payload["git"] = {"mode": "staged", "write_path_count": 2}
        out = render_check_report(payload, format="text")
        assert "Git input: staged diff (2 changed paths)" in out
        assert "Violations: none" in out
        assert "Recommended next action" not in out

    def test_markdown_render_includes_all_branches(self):
        payload = _payload()
        payload["git"] = {
            "mode": "range",
            "write_path_count": 4,
            "base": "main",
            "head": "HEAD",
        }
        violation = payload["violations"][0]
        violation["matched_commands"] = ["pytest"]
        violation["matched_claims"] = ["reviewed"]
        violation["required_paths"] = ["docs/CHANGELOG.md"]
        violation["required_commands"] = ["lint"]
        violation["required_claims"] = ["security-reviewed"]

        out = render_check_report(payload, format="markdown")
        assert "# Policy Explanation" in out
        assert "- **Decision:** `block`" in out
        assert "- **Git input:** main...HEAD (4 changed paths)" in out
        assert "- **Recommended next action:** fix the write" in out
        assert "### `deny-generated` — no generated writes" in out
        assert "- **Matched paths:** `generated/foo.py`" in out
        assert "- **Matched commands:** `pytest`" in out
        assert "- **Required claims:** `security-reviewed`" in out

    def test_markdown_render_staged_git_and_no_violations(self):
        payload = _payload(
            violations=[],
            violation_count=0,
            blocking_violation_count=0,
            next_action=None,
        )
        payload["git"] = {"mode": "staged", "write_path_count": 0}
        out = render_check_report(payload, format="markdown")
        assert "- **Git input:** staged diff (0 changed paths)" in out
        assert "No violations." in out

    def test_unknown_format_raises(self):
        with pytest.raises(ReportError, match="text"):
            render_check_report(_payload(), format="yaml")

    def test_provenance_fallbacks(self):
        payload = _payload(
            violations=[
                _violation(source_path="CLAUDE.md", source_block_id=None),
                _violation(source_path=None, source_block_id="block-2"),
                _violation(source_path=None, source_block_id=None),
            ],
            violation_count=3,
            blocking_violation_count=3,
        )
        out = render_check_report(payload, format="text")
        assert "Rule provenance: CLAUDE.md" in out
        assert "Rule provenance: block-2" in out
        assert "Rule provenance: unknown" in out


class TestLoadFromFileAndText:
    def test_load_from_file_round_trips(self, tmp_path: Path):
        file_path = tmp_path / "report.json"
        file_path.write_text(json.dumps(_payload()), encoding="utf-8")
        report = load_check_report_file(file_path)
        assert report["decision"] == "block"

    def test_load_from_file_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_check_report_file(tmp_path / "missing.json")

    def test_load_from_file_invalid_json(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ReportError, match="not valid JSON"):
            load_check_report_file(bad)

    def test_load_from_text_round_trips(self):
        report = load_check_report_text(json.dumps(_payload()))
        assert report["decision"] == "block"

    def test_load_from_text_invalid_json_uses_source_label(self):
        with pytest.raises(ReportError, match="from stdin"):
            load_check_report_text("{ broken")

    def test_load_from_text_custom_source_label(self):
        with pytest.raises(ReportError, match="from --stdin-report"):
            load_check_report_text("{ broken", source="--stdin-report")
