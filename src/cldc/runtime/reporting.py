from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cldc.errors import ReportError
from cldc.runtime.report_schema import CHECK_REPORT_FORMAT_VERSION, CHECK_REPORT_SCHEMA

ALLOWED_DECISIONS = {"pass", "warn", "block"}


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"report field '{field}' must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field=field)


def _require_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReportError(f"report field '{field}' must be a boolean")
    return value


def _require_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int):
        raise ReportError(f"report field '{field}' must be an integer")
    return value


def _require_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ReportError(f"report field '{field}' must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ReportError(f"report field '{field}[{index}]' must be a non-empty string")
        result.append(item.strip())
    return result


def _normalize_inputs(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ReportError("report field 'inputs' must be a JSON object")
    return {
        "read_paths": _require_string_list(value.get("read_paths", []), field="inputs.read_paths"),
        "write_paths": _require_string_list(value.get("write_paths", []), field="inputs.write_paths"),
        "commands": _require_string_list(value.get("commands", []), field="inputs.commands"),
        "claims": _require_string_list(value.get("claims", []), field="inputs.claims"),
    }


def _normalize_git(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ReportError("report field 'git' must be a JSON object when present")

    normalized: dict[str, Any] = {
        "mode": _require_string(value.get("mode"), field="git.mode"),
        "write_path_count": _require_int(value.get("write_path_count", 0), field="git.write_path_count"),
    }
    for optional_field in ("base", "head"):
        if optional_field in value and value.get(optional_field) is not None:
            normalized[optional_field] = _require_string(value.get(optional_field), field=f"git.{optional_field}")
    if "git_command" in value:
        normalized["git_command"] = _require_string_list(value.get("git_command"), field="git.git_command")
    return normalized


def _normalize_violation(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"report field 'violations[{index}]' must be a JSON object")
    return {
        "rule_id": _require_string(value.get("rule_id"), field=f"violations[{index}].rule_id"),
        "kind": _require_string(value.get("kind"), field=f"violations[{index}].kind"),
        "mode": _require_string(value.get("mode"), field=f"violations[{index}].mode"),
        "message": _require_string(value.get("message"), field=f"violations[{index}].message"),
        "explanation": _require_string(value.get("explanation"), field=f"violations[{index}].explanation"),
        "recommended_action": _require_string(value.get("recommended_action"), field=f"violations[{index}].recommended_action"),
        "matched_paths": _require_string_list(value.get("matched_paths", []), field=f"violations[{index}].matched_paths"),
        "matched_commands": _require_string_list(value.get("matched_commands", []), field=f"violations[{index}].matched_commands"),
        "matched_claims": _require_string_list(value.get("matched_claims", []), field=f"violations[{index}].matched_claims"),
        "required_paths": _require_string_list(value.get("required_paths", []), field=f"violations[{index}].required_paths"),
        "required_commands": _require_string_list(value.get("required_commands", []), field=f"violations[{index}].required_commands"),
        "required_claims": _require_string_list(value.get("required_claims", []), field=f"violations[{index}].required_claims"),
        "source_path": _optional_string(value.get("source_path"), field=f"violations[{index}].source_path"),
        "source_block_id": _optional_string(value.get("source_block_id"), field=f"violations[{index}].source_block_id"),
    }


def load_check_report(payload: Any) -> dict[str, Any]:
    """Validate a saved policy report artifact and normalize its shape."""

    if not isinstance(payload, dict):
        raise ReportError("policy report payload must be a JSON object")

    schema = payload.get("$schema")
    if schema is not None and schema != CHECK_REPORT_SCHEMA:
        raise ReportError("report field '$schema' does not match this explainer; regenerate the report with the current `cldc` version")

    format_version = payload.get("format_version")
    if format_version is not None and format_version != CHECK_REPORT_FORMAT_VERSION:
        raise ReportError(
            "report field 'format_version' does not match this explainer; regenerate the report with the current `cldc` version"
        )

    decision = _require_string(payload.get("decision"), field="decision")
    if decision not in ALLOWED_DECISIONS:
        raise ReportError(f"report field 'decision' must be one of: {', '.join(sorted(ALLOWED_DECISIONS))}")

    violations = payload.get("violations")
    if not isinstance(violations, list):
        raise ReportError("report field 'violations' must be a list")

    normalized = {
        "$schema": CHECK_REPORT_SCHEMA,
        "format_version": CHECK_REPORT_FORMAT_VERSION,
        "ok": _require_bool(payload.get("ok"), field="ok"),
        "repo_root": _require_string(payload.get("repo_root"), field="repo_root"),
        "lockfile_path": _require_string(payload.get("lockfile_path"), field="lockfile_path"),
        "decision": decision,
        "default_mode": _require_string(payload.get("default_mode"), field="default_mode"),
        "summary": _require_string(payload.get("summary"), field="summary"),
        "next_action": _optional_string(payload.get("next_action"), field="next_action"),
        "inputs": _normalize_inputs(payload.get("inputs")),
        "violation_count": _require_int(payload.get("violation_count"), field="violation_count"),
        "blocking_violation_count": _require_int(payload.get("blocking_violation_count"), field="blocking_violation_count"),
        "violations": [_normalize_violation(violation, index=index) for index, violation in enumerate(violations)],
    }
    git_metadata = _normalize_git(payload.get("git"))
    if git_metadata is not None:
        normalized["git"] = git_metadata
    return normalized


def load_check_report_file(path: Path | str) -> dict[str, Any]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"policy report file not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"policy report file is not valid JSON: {exc}") from exc
    return load_check_report(payload)


def load_check_report_text(text: str, *, source: str = "stdin") -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportError(f"policy report from {source} is not valid JSON: {exc}") from exc
    return load_check_report(payload)


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "<none>"


def _provenance(violation: dict[str, Any]) -> str:
    source_path = violation.get("source_path")
    source_block_id = violation.get("source_block_id")
    if source_path and source_block_id:
        return f"{source_path}#{source_block_id}"
    if source_path:
        return str(source_path)
    if source_block_id:
        return str(source_block_id)
    return "unknown"


def render_check_report(payload: dict[str, Any], *, format: str = "text") -> str:
    """Render a validated policy report as text or Markdown."""

    report = load_check_report(payload)
    if format == "markdown":
        return _render_markdown(report)
    if format != "text":
        raise ReportError("report format must be 'text' or 'markdown'")
    return _render_text(report)


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Policy explanation: {report['decision']}",
        f"Summary: {report['summary']}",
        f"Repo root: {report['repo_root']}",
        f"Lockfile: {report['lockfile_path']}",
        f"Default mode: {report['default_mode']}",
    ]

    git_metadata = report.get("git")
    if git_metadata:
        if git_metadata.get("mode") == "staged":
            lines.append(f"Git input: staged diff ({git_metadata.get('write_path_count', 0)} changed paths)")
        else:
            lines.append(
                f"Git input: {git_metadata.get('base')}...{git_metadata.get('head')} "
                f"({git_metadata.get('write_path_count', 0)} changed paths)"
            )

    inputs = report["inputs"]
    lines.append(
        "Evidence inputs: "
        f"reads={len(inputs['read_paths'])}, writes={len(inputs['write_paths'])}, "
        f"commands={len(inputs['commands'])}, claims={len(inputs['claims'])}"
    )
    if report["next_action"]:
        lines.append(f"Recommended next action: {report['next_action']}")

    if not report["violations"]:
        lines.append("Violations: none")
        return "\n".join(lines)

    lines.append("Violations:")
    for index, violation in enumerate(report["violations"], start=1):
        lines.append(f"{index}. [{violation['mode']}] {violation['rule_id']} ({violation['kind']}): {violation['message']}")
        lines.append(f"   Why: {violation['explanation']}")
        lines.append(f"   Next step: {violation['recommended_action']}")
        lines.append(f"   Rule provenance: {_provenance(violation)}")
        if violation["matched_paths"]:
            lines.append(f"   Matched paths: {_join(violation['matched_paths'])}")
        if violation["matched_commands"]:
            lines.append(f"   Matched commands: {_join(violation['matched_commands'])}")
        if violation["matched_claims"]:
            lines.append(f"   Matched claims: {_join(violation['matched_claims'])}")
        if violation["required_paths"]:
            lines.append(f"   Required reads: {_join(violation['required_paths'])}")
        if violation["required_commands"]:
            lines.append(f"   Required commands: {_join(violation['required_commands'])}")
        if violation["required_claims"]:
            lines.append(f"   Required claims: {_join(violation['required_claims'])}")
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Policy Explanation",
        "",
        f"- **Decision:** `{report['decision']}`",
        f"- **Summary:** {report['summary']}",
        f"- **Repo root:** `{report['repo_root']}`",
        f"- **Lockfile:** `{report['lockfile_path']}`",
        f"- **Default mode:** `{report['default_mode']}`",
    ]

    git_metadata = report.get("git")
    if git_metadata:
        if git_metadata.get("mode") == "staged":
            git_summary = f"staged diff ({git_metadata.get('write_path_count', 0)} changed paths)"
        else:
            git_summary = (
                f"{git_metadata.get('base')}...{git_metadata.get('head')} ({git_metadata.get('write_path_count', 0)} changed paths)"
            )
        lines.append(f"- **Git input:** {git_summary}")

    inputs = report["inputs"]
    lines.append(
        f"- **Evidence inputs:** reads={len(inputs['read_paths'])}, writes={len(inputs['write_paths'])}, "
        f"commands={len(inputs['commands'])}, claims={len(inputs['claims'])}"
    )
    if report["next_action"]:
        lines.append(f"- **Recommended next action:** {report['next_action']}")

    lines.extend(["", "## Violations", ""])
    if not report["violations"]:
        lines.append("No violations.")
        return "\n".join(lines)

    for violation in report["violations"]:
        lines.extend(
            [
                f"### `{violation['rule_id']}` — {violation['message']}",
                "",
                f"- **Mode:** `{violation['mode']}`",
                f"- **Kind:** `{violation['kind']}`",
                f"- **Why:** {violation['explanation']}",
                f"- **Next step:** {violation['recommended_action']}",
                f"- **Rule provenance:** `{_provenance(violation)}`",
            ]
        )
        if violation["matched_paths"]:
            lines.append(f"- **Matched paths:** `{_join(violation['matched_paths'])}`")
        if violation["matched_commands"]:
            lines.append(f"- **Matched commands:** `{_join(violation['matched_commands'])}`")
        if violation["matched_claims"]:
            lines.append(f"- **Matched claims:** `{_join(violation['matched_claims'])}`")
        if violation["required_paths"]:
            lines.append(f"- **Required reads:** `{_join(violation['required_paths'])}`")
        if violation["required_commands"]:
            lines.append(f"- **Required commands:** `{_join(violation['required_commands'])}`")
        if violation["required_claims"]:
            lines.append(f"- **Required claims:** `{_join(violation['required_claims'])}`")
        lines.append("")
    return "\n".join(lines).rstrip()
