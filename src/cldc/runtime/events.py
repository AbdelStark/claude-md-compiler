from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cldc.errors import EvidenceError

ALLOWED_EVENT_KINDS = {"read", "write", "command", "claim"}


@dataclass(frozen=True)
class ExecutionInputs:
    """Canonical runtime evidence grouped by reads, writes, commands, and claims."""

    read_paths: list[str]
    write_paths: list[str]
    commands: list[str]
    claims: list[str]

    def merged_with(self, other: ExecutionInputs) -> ExecutionInputs:
        """Return a new `ExecutionInputs` with the fields of `self` followed by `other`.

        Order is preserved (self first, then other) and no deduplication is
        performed — duplicates are the caller's responsibility. Used by the
        CLI to merge explicit `--read`/`--write`/`--command`/`--claim` flags
        with an events-file or stdin payload.
        """

        return ExecutionInputs(
            read_paths=[*self.read_paths, *other.read_paths],
            write_paths=[*self.write_paths, *other.write_paths],
            commands=[*self.commands, *other.commands],
            claims=[*self.claims, *other.claims],
        )


EMPTY_EXECUTION_INPUTS = ExecutionInputs(read_paths=[], write_paths=[], commands=[], claims=[])


def _require_string(value: Any, *, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{context} requires a string '{field}'")
    return value.strip()


def _coerce_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EvidenceError(f"'{field}' must be a JSON array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise EvidenceError(f"'{field}[{index}]' must be a non-empty string")
        result.append(item.strip())
    return result


def _parse_event(event: Any, *, index: int) -> ExecutionInputs:
    if not isinstance(event, dict):
        raise EvidenceError(f"events[{index}] must be a JSON object")

    kind = event.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise EvidenceError(f"events[{index}] must contain a string 'kind'")
    kind = kind.strip()
    if kind not in ALLOWED_EVENT_KINDS:
        allowed = ", ".join(sorted(ALLOWED_EVENT_KINDS))
        raise EvidenceError(f"events[{index}] kind {kind!r} is unsupported; expected one of: {allowed}")

    context = f"events[{index}] kind {kind!r}"
    if kind == "read":
        return ExecutionInputs(
            read_paths=[_require_string(event.get("path"), field="path", context=context)], write_paths=[], commands=[], claims=[]
        )
    if kind == "write":
        return ExecutionInputs(
            read_paths=[], write_paths=[_require_string(event.get("path"), field="path", context=context)], commands=[], claims=[]
        )
    if kind == "command":
        return ExecutionInputs(
            read_paths=[], write_paths=[], commands=[_require_string(event.get("command"), field="command", context=context)], claims=[]
        )
    return ExecutionInputs(
        read_paths=[], write_paths=[], commands=[], claims=[_require_string(event.get("claim"), field="claim", context=context)]
    )


def load_execution_inputs(payload: Any) -> ExecutionInputs:
    """Validate and normalize execution-input JSON into one canonical payload."""

    if not isinstance(payload, dict):
        raise EvidenceError("execution input payload must be a JSON object")

    inputs = ExecutionInputs(
        read_paths=_coerce_string_list(payload.get("read_paths"), field="read_paths"),
        write_paths=_coerce_string_list(payload.get("write_paths"), field="write_paths"),
        commands=_coerce_string_list(payload.get("commands"), field="commands"),
        claims=_coerce_string_list(payload.get("claims"), field="claims"),
    )

    raw_events = payload.get("events")
    if raw_events is None:
        return inputs
    if not isinstance(raw_events, list):
        raise EvidenceError("'events' must be a JSON array")

    merged = inputs
    for index, event in enumerate(raw_events):
        merged = merged.merged_with(_parse_event(event, index=index))
    return merged


def load_execution_inputs_file(path: Path | str) -> ExecutionInputs:
    """Load execution-input JSON from disk and validate its shape."""

    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"execution input payload file not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"execution input payload file is not valid JSON: {exc}") from exc
    return load_execution_inputs(payload)


def load_execution_inputs_text(text: str, *, source: str = "stdin") -> ExecutionInputs:
    """Load execution-input JSON from a text payload."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"execution input payload from {source} is not valid JSON: {exc}") from exc
    return load_execution_inputs(payload)
