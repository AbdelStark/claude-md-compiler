# CLDC-0003: Fix plan

- **Status**: Frozen
- **Created**: 2026-04-07
- **Supersedes**: —
- **Superseded by**: —

## Abstract

`cldc fix` consumes a check report (CLDC-0002) and produces a JSON
artifact called a *fix plan*. The fix plan is a deterministic, ranked
list of remediation hints — one entry per violation in the source
report — designed to be acted on by humans, code review bots, or
future autofix tooling. This RFC freezes its shape.

## Motivation

A check report tells you *what is wrong*. A fix plan tells you *what to
do about it*, in a form a tool can rank, filter, and act on without
having to re-read the original report's prose. We split the two so the
report can stay close to the evaluator and the plan can stay close to
the user, but both are versioned contracts.

## Specification

### Identity

- `$schema`: `https://cldc.dev/schemas/policy-fix-plan/v1` (string,
  required). Defined as `FIX_PLAN_SCHEMA` in
  `src/cldc/runtime/remediation.py`.
- `format_version`: `"1"` (string, required). Defined as
  `FIX_PLAN_FORMAT_VERSION` in the same module.

### Top-level keys

The payload is built by `build_fix_plan` in
`src/cldc/runtime/remediation.py`. Every key listed here is required
and must appear in every well-formed fix plan.

| Key                        | Type             | Notes                                                                          |
|----------------------------|------------------|--------------------------------------------------------------------------------|
| `$schema`                  | string           | Pinned to the value above.                                                     |
| `format_version`           | string           | Pinned to `"1"`.                                                               |
| `ok`                       | boolean          | Always `true` for a successfully built plan; reserved for future use.          |
| `repo_root`                | string           | Copied verbatim from the source report.                                        |
| `lockfile_path`            | string           | Copied verbatim from the source report.                                        |
| `decision`                 | string           | Copied verbatim from the source report.                                        |
| `report_summary`           | string           | The source report's `summary`.                                                 |
| `summary`                  | string           | A plan-specific summary derived from `_remediation_summary`.                   |
| `next_action`              | string \| null   | The first step of the first remediation, or `null` if there are none.          |
| `inputs`                   | object           | Copied verbatim from the source report.                                        |
| `violation_count`          | integer          | Copied verbatim.                                                               |
| `blocking_violation_count` | integer          | Copied verbatim.                                                               |
| `remediation_count`        | integer          | `len(remediations)`.                                                           |
| `remediations`             | array of objects | One entry per source-report violation, in the same order.                      |

### Remediation shape

Each entry in `remediations[]` is a JSON object with the following 14
fields. All array fields are always present; empty arrays are written
as `[]`, never omitted.

| Key                  | Type             | Notes                                                                                       |
|----------------------|------------------|---------------------------------------------------------------------------------------------|
| `rule_id`            | string           | The rule that fired.                                                                        |
| `kind`               | string           | The rule kind.                                                                              |
| `mode`               | string           | The effective mode of the source violation.                                                 |
| `priority`           | string           | `"blocking"` if `mode in {"block", "fix"}`, otherwise `"non-blocking"`.                     |
| `message`            | string           | The source violation's `message`.                                                           |
| `why`                | string           | The source violation's `explanation`.                                                       |
| `recommended_action` | string           | The source violation's `recommended_action`.                                                |
| `suggested_commands` | array of strings | Deduped `required_commands` for `require_command`, otherwise `[]`.                          |
| `suggested_claims`   | array of strings | Deduped `required_claims` for `require_claim` (CLDC-0004), otherwise `[]`.                  |
| `files_to_inspect`   | array of strings | Deduped concatenation of `source_path`, `matched_paths`, `required_paths`. May be empty.    |
| `steps`              | array of strings | 2-3 actionable steps derived from `_steps_for_violation`.                                   |
| `source_path`        | string \| null   | Copied verbatim from the source violation.                                                  |
| `source_block_id`    | string \| null   | Copied verbatim from the source violation.                                                  |
| `can_autofix`        | boolean          | Always `false` in this RFC. Reserved for a future autofix RFC.                              |

`_dedupe` in `src/cldc/runtime/remediation.py` is the only allowed
deduplication for `files_to_inspect`, `suggested_commands`, and
`suggested_claims`: empty strings are dropped, leading/trailing
whitespace is stripped, and the first occurrence of each value wins.

### Priority mapping

```python
def _priority_for_mode(mode: str) -> str:
    return 'blocking' if mode in {'block', 'fix'} else 'non-blocking'
```

This mapping is part of the contract. A consumer that filters on
`priority == "blocking"` is guaranteed to see exactly the violations
whose `blocking_violation_count` was non-zero in the source report.

### `can_autofix`

`can_autofix` is wired to a literal `False` in this RFC. Producers must
not emit `true` and consumers must reject any plan whose
`remediations[].can_autofix` is `true`. The field exists so a future
RFC can flip it to `true` for specific rule kinds without changing the
JSON shape — when that happens, the future RFC will define exactly
which kinds may set it and what executing an autofix means.

### Rendering

`render_fix_plan` in `src/cldc/runtime/remediation.py` knows how to
render a plan as `text` or `markdown`. Those text/markdown forms are
**not normative**: only the JSON shape is. Renderers may evolve their
wording across releases without bumping the schema.

## Compatibility

A consumer at this `$schema` URL **must**:

- Reject the plan when `$schema` is missing or different.
- Reject the plan when `format_version` is missing or different.
- Reject the plan when any required key in the top-level object or any
  remediation entry is missing or has the wrong type.
- Reject the plan when any `remediations[].can_autofix` is `true`.
- Treat all 14 remediation fields as required and never omit array
  fields when re-serializing.

These checks are implemented by `_normalize_fix_plan` in
`src/cldc/runtime/remediation.py`.

## Validation

Test surface that locks in this contract today:

- `tests/test_runtime.py` — fix-plan generation for every rule kind,
  priority mapping, dedupe behavior.
- `tests/test_cli.py` — `cldc fix` JSON output and exit codes,
  round-trip via saved report.

## Reference

- `src/cldc/runtime/remediation.py` — `FIX_PLAN_SCHEMA`,
  `FIX_PLAN_FORMAT_VERSION`, `build_fix_plan`, `_priority_for_mode`,
  `_files_to_inspect`, `_suggested_commands`, `_suggested_claims`,
  `_steps_for_violation`, `_normalize_fix_plan`, `render_fix_plan`.
- `src/cldc/runtime/reporting.py` — `load_check_report`, used by
  `build_fix_plan` to validate its input.

## Appendix: minimal valid example

Abbreviated output of `cldc fix tests/fixtures/repo_a --write src/main.py --json`:

```json
{
  "$schema": "https://cldc.dev/schemas/policy-fix-plan/v1",
  "format_version": "1",
  "ok": true,
  "repo_root": "/abs/path/to/repo",
  "lockfile_path": ".claude/policy.lock.json",
  "decision": "warn",
  "report_summary": "Policy check found 1 non-blocking violation(s).",
  "summary": "Generated 1 remediation plan item(s) for 1 violation(s) in a `warn` policy report.",
  "next_action": "Read at least one required context path before keeping changes to src/main.py: docs/rfcs/**.",
  "inputs": {
    "read_paths": [],
    "write_paths": ["src/main.py"],
    "commands": [],
    "claims": []
  },
  "violation_count": 1,
  "blocking_violation_count": 0,
  "remediation_count": 1,
  "remediations": [
    {
      "rule_id": "must-read-rfc",
      "kind": "require_read",
      "mode": "warn",
      "priority": "non-blocking",
      "message": "Read the RFCs before touching source.",
      "why": "Write activity src/main.py triggered require_read rule 'must-read-rfc', but no required read matched docs/rfcs/**.",
      "recommended_action": "Read at least one path matching docs/rfcs/** before modifying src/main.py.",
      "suggested_commands": [],
      "suggested_claims": [],
      "files_to_inspect": [".claude-compiler.yaml", "src/main.py", "docs/rfcs/**"],
      "steps": [
        "Read at least one required context path before keeping changes to src/main.py: docs/rfcs/**.",
        "Re-check the change against the guidance from docs/rfcs/** and update the implementation if needed.",
        "Re-run `cldc check` or `cldc ci` after the required context has been reviewed."
      ],
      "source_path": ".claude-compiler.yaml",
      "source_block_id": null,
      "can_autofix": false
    }
  ]
}
```
