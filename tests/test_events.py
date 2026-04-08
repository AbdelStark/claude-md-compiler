"""Tests for `cldc.runtime.events`.

Covers the file/text loader paths, every error branch in
`load_execution_inputs`, and the `ExecutionInputs.merged_with` /
`is_empty`-style invariants. The bulk-shape happy path is exercised
in `tests/test_runtime.py`; this module focuses on the loader API and
edge cases that the property tests cannot easily express.
"""

from __future__ import annotations

import json

import pytest

from cldc.errors import EvidenceError
from cldc.runtime.events import (
    EMPTY_EXECUTION_INPUTS,
    CommandResult,
    ExecutionInputs,
    load_execution_inputs,
    load_execution_inputs_file,
    load_execution_inputs_text,
)

# --- ExecutionInputs ---------------------------------------------------------


class TestExecutionInputs:
    def test_merged_with_concatenates_in_order_without_dedup(self):
        first = ExecutionInputs(
            read_paths=["a"],
            write_paths=["b"],
            commands=["c"],
            claims=["d"],
            command_results=[CommandResult(command="c", outcome="success")],
        )
        second = ExecutionInputs(
            read_paths=["a", "e"],
            write_paths=["b"],
            commands=["c"],
            claims=["d"],
            command_results=[CommandResult(command="c", outcome="failure")],
        )

        merged = first.merged_with(second)

        # Order is preserved (self first, then other) and duplicates are kept.
        assert merged.read_paths == ["a", "a", "e"]
        assert merged.write_paths == ["b", "b"]
        assert merged.commands == ["c", "c"]
        assert merged.claims == ["d", "d"]
        assert merged.command_results == [
            CommandResult(command="c", outcome="success"),
            CommandResult(command="c", outcome="failure"),
        ]

    def test_empty_singleton_round_trips_through_merged_with(self):
        merged = EMPTY_EXECUTION_INPUTS.merged_with(EMPTY_EXECUTION_INPUTS)
        assert merged == EMPTY_EXECUTION_INPUTS


# --- load_execution_inputs (in-memory dict) ---------------------------------


class TestLoadExecutionInputs:
    def test_returns_empty_inputs_for_empty_dict(self):
        assert load_execution_inputs({}) == EMPTY_EXECUTION_INPUTS

    def test_supports_bulk_lists_only(self):
        payload = {
            "read_paths": ["docs/spec.md"],
            "write_paths": ["src/main.py"],
            "commands": ["pytest"],
            "claims": ["ci-green"],
        }

        inputs = load_execution_inputs(payload)

        assert inputs.read_paths == ["docs/spec.md"]
        assert inputs.write_paths == ["src/main.py"]
        assert inputs.commands == ["pytest"]
        assert inputs.claims == ["ci-green"]
        assert inputs.command_results == []

    def test_supports_bulk_command_results(self):
        payload = {
            "command_results": [
                {"command": "pytest -q", "outcome": "success"},
                {"command": "ruff check .", "outcome": "failure"},
            ]
        }

        inputs = load_execution_inputs(payload)

        assert inputs.command_results == [
            CommandResult(command="pytest -q", outcome="success"),
            CommandResult(command="ruff check .", outcome="failure"),
        ]

    def test_merges_bulk_lists_and_events(self):
        payload = {
            "read_paths": ["docs/spec.md"],
            "events": [
                {"kind": "read", "path": "docs/extra.md"},
                {"kind": "write", "path": "src/util.py"},
                {"kind": "command", "command": "pytest -q", "outcome": "success"},
            ],
        }

        inputs = load_execution_inputs(payload)

        assert inputs.read_paths == ["docs/spec.md", "docs/extra.md"]
        assert inputs.write_paths == ["src/util.py"]
        assert inputs.commands == ["pytest -q"]
        assert inputs.command_results == [CommandResult(command="pytest -q", outcome="success")]

    def test_rejects_non_dict_payload(self):
        with pytest.raises(EvidenceError, match="must be a JSON object"):
            load_execution_inputs("not a dict")

    def test_rejects_non_list_events(self):
        with pytest.raises(EvidenceError, match="'events' must be a JSON array"):
            load_execution_inputs({"events": "nope"})

    def test_rejects_non_list_bulk_field(self):
        with pytest.raises(EvidenceError, match="'read_paths' must be a JSON array"):
            load_execution_inputs({"read_paths": "docs/spec.md"})

    def test_rejects_empty_string_in_bulk_field(self):
        with pytest.raises(EvidenceError, match=r"'read_paths\[0\]'"):
            load_execution_inputs({"read_paths": ["   "]})

    def test_rejects_unknown_event_kind(self):
        with pytest.raises(EvidenceError, match="kind 'shrug' is unsupported"):
            load_execution_inputs({"events": [{"kind": "shrug"}]})

    def test_rejects_event_missing_command_field(self):
        with pytest.raises(EvidenceError, match="kind 'command' requires a string 'command'"):
            load_execution_inputs({"events": [{"kind": "command"}]})

    def test_rejects_invalid_command_result_outcome(self):
        with pytest.raises(EvidenceError, match="must be one of: failure, success"):
            load_execution_inputs({"command_results": [{"command": "pytest -q", "outcome": "maybe"}]})

    def test_rejects_event_missing_claim_field(self):
        with pytest.raises(EvidenceError, match="kind 'claim' requires a string 'claim'"):
            load_execution_inputs({"events": [{"kind": "claim"}]})

    def test_rejects_non_dict_event(self):
        with pytest.raises(EvidenceError, match=r"events\[0\] must be a JSON object"):
            load_execution_inputs({"events": ["not a dict"]})


# --- load_execution_inputs_file ----------------------------------------------


class TestLoadExecutionInputsFile:
    def test_loads_payload_from_disk(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text(json.dumps({"write_paths": ["src/main.py"]}), encoding="utf-8")

        inputs = load_execution_inputs_file(path)

        assert inputs.write_paths == ["src/main.py"]

    def test_raises_file_not_found_with_actionable_message(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="execution input payload file not found"):
            load_execution_inputs_file(tmp_path / "missing.json")

    def test_raises_evidence_error_for_invalid_json(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(EvidenceError, match="not valid JSON"):
            load_execution_inputs_file(path)


# --- load_execution_inputs_text ----------------------------------------------


class TestLoadExecutionInputsText:
    def test_loads_payload_from_text(self):
        inputs = load_execution_inputs_text(json.dumps({"commands": ["pytest -q"]}))

        assert inputs.commands == ["pytest -q"]

    def test_raises_evidence_error_for_invalid_json_with_source_label(self):
        with pytest.raises(EvidenceError, match="from stdin is not valid JSON"):
            load_execution_inputs_text("{not json")

    def test_uses_custom_source_label_in_error(self):
        with pytest.raises(EvidenceError, match="from inline-payload"):
            load_execution_inputs_text("{not json", source="inline-payload")
