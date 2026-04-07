"""Tests for the typed exception hierarchy in `cldc.errors`."""

from __future__ import annotations

import json

import pytest

from cldc import (
    CldcError,
    EvidenceError,
    LockfileError,
    PolicySourceError,
    PresetError,
    PresetNotFoundError,
    RepoBoundaryError,
    ReportError,
    RuleValidationError,
)
from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents
from cldc.presets import load_preset
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.events import load_execution_inputs


def test_cldc_error_subclasses_value_error():
    """Back-compat: every cldc error must remain catchable as ValueError."""

    assert issubclass(CldcError, ValueError)
    assert issubclass(PolicySourceError, CldcError)
    assert issubclass(RuleValidationError, CldcError)
    assert issubclass(LockfileError, CldcError)
    assert issubclass(EvidenceError, CldcError)
    assert issubclass(ReportError, CldcError)
    assert issubclass(PresetError, CldcError)
    assert issubclass(RepoBoundaryError, CldcError)
    assert issubclass(PresetNotFoundError, PresetError)
    assert issubclass(PresetNotFoundError, LookupError)


def test_policy_source_error_for_malformed_extends(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# repo\n", encoding="utf-8")
    (tmp_path / ".claude-compiler.yaml").write_text(
        "default_mode: warn\nextends: not-a-list\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicySourceError, match="extends must be a list"):
        load_policy_sources(tmp_path)


def test_rule_validation_error_for_duplicate_rule_ids(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: dup\n    kind: deny_write\n    paths: ['a/**']\n    message: first\n```\n",
        encoding="utf-8",
    )
    (tmp_path / ".claude-compiler.yaml").write_text(
        "rules:\n  - id: dup\n    kind: deny_write\n    paths: ['b/**']\n    message: second\n",
        encoding="utf-8",
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(RuleValidationError, match="duplicate rule id"):
        parse_rule_documents(bundle)


def test_rule_validation_error_for_missing_required_field(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: missing-claims\n    kind: require_claim\n    when_paths: ['src/**']\n    message: needs claim\n```\n",
        encoding="utf-8",
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(RuleValidationError, match="requires field 'claims'"):
        parse_rule_documents(bundle)


def test_lockfile_error_for_schema_drift(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / ".claude" / "policy.lock.json"
    payload = json.loads(lockfile.read_text(encoding="utf-8"))
    payload["$schema"] = "https://cldc.dev/schemas/policy-lock/v0"
    lockfile.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LockfileError, match="schema does not match"):
        check_repo_policy(tmp_path, write_paths=["generated/output.json"])


def test_evidence_error_for_malformed_event_payload():
    with pytest.raises(EvidenceError, match="requires a string 'path'"):
        load_execution_inputs({"events": [{"kind": "write"}]})


def test_repo_boundary_error_for_path_outside_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)

    outside_path = (tmp_path.parent / "escape.txt").as_posix()

    with pytest.raises(RepoBoundaryError, match="resolves outside the discovered repo root"):
        check_repo_policy(tmp_path, write_paths=[outside_path])


def test_preset_not_found_error_keeps_legacy_catchability():
    with pytest.raises(PresetNotFoundError, match="not bundled with this cldc version"):
        load_preset("definitely-not-a-bundled-preset")

    # Confirm it is reachable through every layer of the hierarchy.
    for parent in (PresetError, CldcError, ValueError, LookupError):
        with pytest.raises(parent):
            load_preset("definitely-not-a-bundled-preset")
