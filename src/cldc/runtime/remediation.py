from __future__ import annotations

from typing import Any

from cldc.runtime.reporting import load_check_report

FIX_PLAN_SCHEMA = "https://cldc.dev/schemas/policy-fix-plan/v1"
FIX_PLAN_FORMAT_VERSION = "1"


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fix plan field '{field}' must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field=field)


def _require_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"fix plan field '{field}' must be a boolean")
    return value


def _require_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"fix plan field '{field}' must be an integer")
    return value


def _require_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"fix plan field '{field}' must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_string(item, field=f"{field}[{index}]"))
    return result


def _normalize_inputs(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("fix plan field 'inputs' must be a JSON object")
    return {
        'read_paths': _require_string_list(value.get('read_paths', []), field='inputs.read_paths'),
        'write_paths': _require_string_list(value.get('write_paths', []), field='inputs.write_paths'),
        'commands': _require_string_list(value.get('commands', []), field='inputs.commands'),
        'claims': _require_string_list(value.get('claims', []), field='inputs.claims'),
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _priority_for_mode(mode: str) -> str:
    return 'blocking' if mode in {'block', 'fix'} else 'non-blocking'


def _files_to_inspect(violation: dict[str, Any]) -> list[str]:
    files: list[str] = []
    source_path = violation.get('source_path')
    if isinstance(source_path, str) and source_path.strip():
        files.append(source_path.strip())
    files.extend(violation.get('matched_paths', []))
    files.extend(violation.get('required_paths', []))
    return _dedupe(files)


def _suggested_commands(violation: dict[str, Any]) -> list[str]:
    if violation['kind'] == 'require_command':
        return _dedupe(violation.get('required_commands', []))
    return []


def _suggested_claims(violation: dict[str, Any]) -> list[str]:
    if violation['kind'] == 'require_claim':
        return _dedupe(violation.get('required_claims', []))
    return []


def _steps_for_violation(violation: dict[str, Any]) -> list[str]:
    matched_paths = violation.get('matched_paths', [])
    matched_display = ', '.join(matched_paths) if matched_paths else 'the affected paths'
    required_paths = violation.get('required_paths', [])
    required_path_display = ', '.join(required_paths) if required_paths else 'the required policy context'
    required_commands = violation.get('required_commands', [])
    required_command_display = ', '.join(required_commands) if required_commands else 'the required validation commands'
    required_claims = violation.get('required_claims', [])
    required_claim_display = ', '.join(required_claims) if required_claims else 'the required policy claims'

    if violation['kind'] == 'deny_write':
        return [
            f"Inspect why {matched_display} changed and decide whether the edit should be reverted, regenerated, or moved to an allowed path.",
            f"Update the change so paths matched by rule '{violation['rule_id']}' are no longer written.",
            "Re-run `cldc check` or `cldc ci` after the prohibited write set is clean.",
        ]
    if violation['kind'] == 'require_read':
        return [
            f"Read at least one required context path before keeping changes to {matched_display}: {required_path_display}.",
            f"Re-check the change against the guidance from {required_path_display} and update the implementation if needed.",
            "Re-run `cldc check` or `cldc ci` after the required context has been reviewed.",
        ]
    if violation['kind'] == 'require_command':
        return [
            f"Run the required validation command(s) before finishing work on {matched_display}: {required_command_display}.",
            "Review the command output and address any failures before marking the change complete.",
            "Re-run `cldc check` or `cldc ci` after validation succeeds.",
        ]
    if violation['kind'] == 'couple_change':
        return [
            f"Update at least one coupled path alongside {matched_display}: {required_path_display}.",
            f"Review whether the change in {matched_display} should also update tests, docs, or related files matched by {required_path_display}.",
            "Re-run `cldc check` or `cldc ci` after the coupled change is included.",
        ]
    if violation['kind'] == 'require_claim':
        return [
            f"Record at least one required claim before keeping changes to {matched_display}: {required_claim_display}.",
            f"Confirm the workflow that produces {required_claim_display} has actually completed (sign-off, review, acknowledgement) and pass the claim with --claim or via an execution-input payload.",
            "Re-run `cldc check` or `cldc ci` after the claim is asserted.",
        ]
    return [
        "Inspect the matched rule and evidence to understand why the policy fired.",
        "Update the change or workflow to satisfy the rule, then re-run the policy check.",
    ]


def _remediation_summary(report: dict[str, Any], remediation_count: int) -> str:
    if remediation_count == 0:
        return 'No remediation is required because the policy report has no violations.'
    return (
        f"Generated {remediation_count} remediation plan item(s) for "
        f"{report['violation_count']} violation(s) in a `{report['decision']}` policy report."
    )


def _next_action(remediations: list[dict[str, Any]]) -> str | None:
    if not remediations:
        return None
    return remediations[0]['steps'][0]


def build_fix_plan(report_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic remediation plan from a policy report artifact."""

    report = load_check_report(report_payload)
    remediations: list[dict[str, Any]] = []

    for violation in report['violations']:
        remediations.append(
            {
                'rule_id': violation['rule_id'],
                'kind': violation['kind'],
                'mode': violation['mode'],
                'priority': _priority_for_mode(violation['mode']),
                'message': violation['message'],
                'why': violation['explanation'],
                'recommended_action': violation['recommended_action'],
                'suggested_commands': _suggested_commands(violation),
                'suggested_claims': _suggested_claims(violation),
                'files_to_inspect': _files_to_inspect(violation),
                'steps': _steps_for_violation(violation),
                'source_path': violation.get('source_path'),
                'source_block_id': violation.get('source_block_id'),
                'can_autofix': False,
            }
        )

    return {
        '$schema': FIX_PLAN_SCHEMA,
        'format_version': FIX_PLAN_FORMAT_VERSION,
        'ok': True,
        'repo_root': report['repo_root'],
        'lockfile_path': report['lockfile_path'],
        'decision': report['decision'],
        'report_summary': report['summary'],
        'summary': _remediation_summary(report, len(remediations)),
        'next_action': _next_action(remediations),
        'inputs': report['inputs'],
        'violation_count': report['violation_count'],
        'blocking_violation_count': report['blocking_violation_count'],
        'remediation_count': len(remediations),
        'remediations': remediations,
    }


def _normalize_fix_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('fix plan payload must be a JSON object')
    if payload.get('$schema') != FIX_PLAN_SCHEMA:
        raise ValueError("fix plan field '$schema' does not match this renderer")
    if payload.get('format_version') != FIX_PLAN_FORMAT_VERSION:
        raise ValueError("fix plan field 'format_version' does not match this renderer")

    remediations = payload.get('remediations')
    if not isinstance(remediations, list):
        raise ValueError("fix plan field 'remediations' must be a list")

    normalized_remediations: list[dict[str, Any]] = []
    for index, remediation in enumerate(remediations):
        if not isinstance(remediation, dict):
            raise ValueError(f"fix plan field 'remediations[{index}]' must be a JSON object")
        normalized_remediations.append(
            {
                'rule_id': _require_string(remediation.get('rule_id'), field=f'remediations[{index}].rule_id'),
                'kind': _require_string(remediation.get('kind'), field=f'remediations[{index}].kind'),
                'mode': _require_string(remediation.get('mode'), field=f'remediations[{index}].mode'),
                'priority': _require_string(remediation.get('priority'), field=f'remediations[{index}].priority'),
                'message': _require_string(remediation.get('message'), field=f'remediations[{index}].message'),
                'why': _require_string(remediation.get('why'), field=f'remediations[{index}].why'),
                'recommended_action': _require_string(
                    remediation.get('recommended_action'), field=f'remediations[{index}].recommended_action'
                ),
                'suggested_commands': _require_string_list(
                    remediation.get('suggested_commands', []), field=f'remediations[{index}].suggested_commands'
                ),
                'suggested_claims': _require_string_list(
                    remediation.get('suggested_claims', []), field=f'remediations[{index}].suggested_claims'
                ),
                'files_to_inspect': _require_string_list(
                    remediation.get('files_to_inspect', []), field=f'remediations[{index}].files_to_inspect'
                ),
                'steps': _require_string_list(remediation.get('steps', []), field=f'remediations[{index}].steps'),
                'source_path': _optional_string(remediation.get('source_path'), field=f'remediations[{index}].source_path'),
                'source_block_id': _optional_string(
                    remediation.get('source_block_id'), field=f'remediations[{index}].source_block_id'
                ),
                'can_autofix': _require_bool(remediation.get('can_autofix'), field=f'remediations[{index}].can_autofix'),
            }
        )

    return {
        '$schema': FIX_PLAN_SCHEMA,
        'format_version': FIX_PLAN_FORMAT_VERSION,
        'ok': _require_bool(payload.get('ok'), field='ok'),
        'repo_root': _require_string(payload.get('repo_root'), field='repo_root'),
        'lockfile_path': _require_string(payload.get('lockfile_path'), field='lockfile_path'),
        'decision': _require_string(payload.get('decision'), field='decision'),
        'report_summary': _require_string(payload.get('report_summary'), field='report_summary'),
        'summary': _require_string(payload.get('summary'), field='summary'),
        'next_action': _optional_string(payload.get('next_action'), field='next_action'),
        'inputs': _normalize_inputs(payload.get('inputs', {})),
        'violation_count': _require_int(payload.get('violation_count'), field='violation_count'),
        'blocking_violation_count': _require_int(
            payload.get('blocking_violation_count'), field='blocking_violation_count'
        ),
        'remediation_count': _require_int(payload.get('remediation_count'), field='remediation_count'),
        'remediations': normalized_remediations,
    }


def render_fix_plan(payload: dict[str, Any], *, format: str = 'text') -> str:
    """Render a fix plan as text or Markdown."""

    if isinstance(payload, dict) and payload.get('$schema') == FIX_PLAN_SCHEMA:
        plan = _normalize_fix_plan(payload)
    else:
        plan = build_fix_plan(payload)
    if format == 'markdown':
        return _render_markdown(plan)
    if format != 'text':
        raise ValueError("fix plan format must be 'text' or 'markdown'")
    return _render_text(plan)


def _render_text(plan: dict[str, Any]) -> str:
    lines = [
        f"Policy fix plan: {plan['decision']}",
        f"Summary: {plan['summary']}",
        f"Policy report summary: {plan['report_summary']}",
        f"Repo root: {plan['repo_root']}",
        f"Lockfile: {plan['lockfile_path']}",
        f"Remediations: {plan['remediation_count']}",
    ]
    if plan['next_action']:
        lines.append(f"Recommended next action: {plan['next_action']}")
    if not plan['remediations']:
        lines.append('Remediations: none')
        return '\n'.join(lines)

    for index, remediation in enumerate(plan['remediations'], start=1):
        lines.append(
            f"{index}. [{remediation['priority']}] {remediation['rule_id']} ({remediation['kind']}): {remediation['message']}"
        )
        lines.append(f"   Why: {remediation['why']}")
        lines.append(f"   Rule recommendation: {remediation['recommended_action']}")
        if remediation['files_to_inspect']:
            lines.append(f"   Files to inspect: {', '.join(remediation['files_to_inspect'])}")
        if remediation['suggested_commands']:
            lines.append(f"   Suggested commands: {', '.join(remediation['suggested_commands'])}")
        if remediation['suggested_claims']:
            lines.append(f"   Suggested claims: {', '.join(remediation['suggested_claims'])}")
        lines.append('   Steps:')
        for step in remediation['steps']:
            lines.append(f"   - {step}")
    return '\n'.join(lines)


def _render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        '# Policy Fix Plan',
        '',
        f"- **Decision:** `{plan['decision']}`",
        f"- **Summary:** {plan['summary']}",
        f"- **Policy report summary:** {plan['report_summary']}",
        f"- **Repo root:** `{plan['repo_root']}`",
        f"- **Lockfile:** `{plan['lockfile_path']}`",
        f"- **Remediations:** `{plan['remediation_count']}`",
    ]
    if plan['next_action']:
        lines.append(f"- **Recommended next action:** {plan['next_action']}")
    lines.extend(['', '## Remediations', ''])
    if not plan['remediations']:
        lines.append('No remediation is required.')
        return '\n'.join(lines)

    for remediation in plan['remediations']:
        lines.extend(
            [
                f"### `{remediation['rule_id']}` — {remediation['message']}",
                '',
                f"- **Priority:** `{remediation['priority']}`",
                f"- **Kind:** `{remediation['kind']}`",
                f"- **Why:** {remediation['why']}",
                f"- **Rule recommendation:** {remediation['recommended_action']}",
            ]
        )
        if remediation['files_to_inspect']:
            lines.append(f"- **Files to inspect:** `{', '.join(remediation['files_to_inspect'])}`")
        if remediation['suggested_commands']:
            lines.append(f"- **Suggested commands:** `{', '.join(remediation['suggested_commands'])}`")
        if remediation['suggested_claims']:
            lines.append(f"- **Suggested claims:** `{', '.join(remediation['suggested_claims'])}`")
        lines.append('- **Steps:**')
        for step in remediation['steps']:
            lines.append(f"  - {step}")
        lines.append('')
    return '\n'.join(lines).rstrip()
