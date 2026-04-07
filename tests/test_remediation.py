"""Tests for `cldc.runtime.remediation`.

Covers `_normalize_fix_plan`'s validation paths, the boundary between
fresh-payload-build and already-versioned re-rendering, and the typed
errors that downstream tools rely on.

The happy-path coverage for `build_fix_plan` and `render_fix_plan` lives in
`tests/test_runtime.py`; this module focuses on schema-drift, malformed-list,
and missing-field rejections.
"""

from __future__ import annotations

import pytest

from cldc.errors import ReportError
from cldc.runtime.remediation import (
    FIX_PLAN_FORMAT_VERSION,
    FIX_PLAN_SCHEMA,
    render_fix_plan,
)

_VALID_REMEDIATION = {
    "rule_id": "demo",
    "kind": "deny_write",
    "mode": "block",
    "priority": "blocking",
    "message": "Do not edit generated files.",
    "why": "Write activity matched deny_write rule.",
    "recommended_action": "Revert the change.",
    "suggested_commands": [],
    "forbidden_commands": [],
    "suggested_claims": [],
    "files_to_inspect": ["generated/output.json"],
    "steps": ["Revert the change."],
    "source_path": "CLAUDE.md",
    "source_block_id": "CLAUDE.md:1",
    "can_autofix": False,
}

_VALID_FIX_PLAN = {
    "$schema": FIX_PLAN_SCHEMA,
    "format_version": FIX_PLAN_FORMAT_VERSION,
    "ok": True,
    "repo_root": "/tmp/repo",
    "lockfile_path": ".claude/policy.lock.json",
    "decision": "block",
    "report_summary": "1 violation",
    "summary": "Generated 1 remediation plan item(s).",
    "next_action": "Revert the change.",
    "inputs": {"read_paths": [], "write_paths": [], "commands": [], "claims": []},
    "violation_count": 1,
    "blocking_violation_count": 1,
    "remediation_count": 1,
    "remediations": [_VALID_REMEDIATION],
}


def test_render_fix_plan_round_trips_valid_payload():
    rendered = render_fix_plan(_VALID_FIX_PLAN, format="text")
    assert "demo" in rendered
    assert "blocking" in rendered


def test_render_fix_plan_rejects_unknown_format():
    with pytest.raises(ReportError, match="format must be 'text' or 'markdown'"):
        render_fix_plan(_VALID_FIX_PLAN, format="json")


def test_normalize_fix_plan_rejects_non_dict_payload():
    with pytest.raises(ReportError, match="must be a JSON object"):
        # Pass a list to force the typed branch.
        render_fix_plan([_VALID_FIX_PLAN])  # type: ignore[arg-type]


def test_normalize_fix_plan_rejects_schema_drift():
    drifted = {**_VALID_FIX_PLAN, "$schema": "https://other/v1"}
    # Schema mismatch routes through build_fix_plan, which calls
    # load_check_report under the hood and rejects the unknown schema.
    with pytest.raises(ReportError):
        render_fix_plan(drifted)


def test_normalize_fix_plan_rejects_format_version_mismatch():
    drifted = {**_VALID_FIX_PLAN, "format_version": "999"}
    with pytest.raises(ReportError, match="format_version"):
        render_fix_plan(drifted)


def test_normalize_fix_plan_rejects_non_list_remediations():
    bad = {**_VALID_FIX_PLAN, "remediations": "nope"}
    with pytest.raises(ReportError, match="'remediations' must be a list"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_non_dict_remediation_item():
    bad = {**_VALID_FIX_PLAN, "remediations": ["nope"]}
    with pytest.raises(ReportError, match=r"remediations\[0\]"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_missing_rule_id():
    bad_remediation = {**_VALID_REMEDIATION}
    bad_remediation["rule_id"] = ""
    bad = {**_VALID_FIX_PLAN, "remediations": [bad_remediation]}
    with pytest.raises(ReportError, match=r"remediations\[0\]\.rule_id"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_non_bool_can_autofix():
    bad_remediation = {**_VALID_REMEDIATION, "can_autofix": "no"}
    bad = {**_VALID_FIX_PLAN, "remediations": [bad_remediation]}
    with pytest.raises(ReportError, match=r"can_autofix.*must be a boolean"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_non_int_violation_count():
    bad = {**_VALID_FIX_PLAN, "violation_count": "1"}
    with pytest.raises(ReportError, match=r"violation_count.*must be an integer"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_non_dict_inputs():
    bad = {**_VALID_FIX_PLAN, "inputs": []}
    with pytest.raises(ReportError, match=r"inputs.*must be a JSON object"):
        render_fix_plan(bad)


def test_normalize_fix_plan_rejects_non_string_input_list_item():
    bad = {
        **_VALID_FIX_PLAN,
        "inputs": {"read_paths": [42], "write_paths": [], "commands": [], "claims": []},
    }
    with pytest.raises(ReportError):
        render_fix_plan(bad)


def test_normalize_fix_plan_keeps_optional_source_fields_nullable():
    optional_remediation = {**_VALID_REMEDIATION, "source_path": None, "source_block_id": None}
    plan = {**_VALID_FIX_PLAN, "remediations": [optional_remediation]}
    rendered = render_fix_plan(plan, format="markdown")
    assert "demo" in rendered
