# CLDC-0002: Check report

- **Status**: Frozen
- **Created**: 2026-04-07
- **Supersedes**: —
- **Superseded by**: —

## Abstract

`cldc check`, `cldc ci`, and `cldc explain` produce — and `cldc explain`
and `cldc fix` consume — a JSON artifact called a *check report*. This
RFC freezes its shape so reports can be saved, transported between
processes, and replayed by `cldc fix` without re-running evaluation.

## Motivation

The check report is the boundary between policy evaluation and the
humans (or downstream tools) that act on the results. Stable shape
matters more than pretty printing: CI systems will store reports as
build artifacts, code review bots will diff them across runs, and
`cldc fix` will rebuild remediation plans from them weeks later. We
freeze the schema so all of those consumers can rely on a single,
versioned shape.

## Specification

### Identity

- `$schema`: `https://cldc.dev/schemas/policy-report/v1` (string,
  required on every freshly emitted report). Defined as
  `CHECK_REPORT_SCHEMA` in `src/cldc/runtime/report_schema.py`.
- `format_version`: `"1"` (string, required on every freshly emitted
  report). Defined as `CHECK_REPORT_FORMAT_VERSION` in the same module.

### Top-level keys

The payload is the result of `CheckReport.to_dict()` in
`src/cldc/runtime/evaluator.py`. Every key listed here is required and
must appear in every freshly emitted report.

| Key                        | Type                       | Notes                                                                              |
|----------------------------|----------------------------|------------------------------------------------------------------------------------|
| `$schema`                  | string                     | Pinned to the value above.                                                         |
| `format_version`           | string                     | Pinned to `"1"`.                                                                   |
| `ok`                       | boolean                    | `false` if any blocking violation was found; otherwise `true`.                     |
| `repo_root`                | string                     | Absolute path to the discovered repository root.                                   |
| `lockfile_path`            | string                     | Always `".claude/policy.lock.json"`.                                               |
| `decision`                 | string                     | One of `pass`, `warn`, `block`. See "Decision values" below.                       |
| `default_mode`             | string                     | The lockfile's `default_mode`.                                                     |
| `summary`                  | string                     | Single-sentence human summary derived from the violation counts.                   |
| `next_action`              | string \| null             | First blocking violation's `recommended_action`, or the first non-blocking one.    |
| `inputs`                   | object                     | Normalized evidence, see "Inputs" below.                                           |
| `violation_count`          | integer                    | `len(violations)`.                                                                 |
| `blocking_violation_count` | integer                    | Number of violations whose effective `mode` is `block` or `fix`.                   |
| `violations`               | array of objects           | One entry per matched rule. See "Violation shape" below.                           |
| `git`                      | object \| omitted          | Present only when the report was produced by `cldc ci`. See "Git metadata".        |

### Decision values

`decision` is computed in `check_repo_policy` after every rule has been
evaluated:

| Decision | Condition                                                              |
|----------|------------------------------------------------------------------------|
| `pass`   | `len(violations) == 0`.                                                |
| `warn`   | At least one violation, but `blocking_violation_count == 0`.           |
| `block`  | `blocking_violation_count > 0`.                                        |

### Inputs

`inputs` is a JSON object with exactly four keys, each an array of
strings normalized to repo-relative POSIX paths or trimmed command/claim
strings. All four keys are always present, even when empty.

```json
{
  "read_paths": ["..."],
  "write_paths": ["..."],
  "commands": ["..."],
  "claims": ["..."]
}
```

Path inputs are validated by `_normalize_paths` in
`src/cldc/runtime/evaluator.py`: any path that resolves outside the
discovered repo root is rejected before evaluation runs.

### Violation shape

Each entry in `violations[]` is the result of `Violation.to_dict()` in
`src/cldc/runtime/evaluator.py`:

| Key                  | Type             | Notes                                                                                   |
|----------------------|------------------|-----------------------------------------------------------------------------------------|
| `rule_id`            | string           | The rule that fired.                                                                    |
| `kind`               | string           | One of the supported rule kinds (see CLDC-0001).                                        |
| `mode`               | string           | The effective mode after `default_mode` fallback.                                       |
| `message`            | string           | The rule's human message, copied verbatim.                                              |
| `explanation`        | string           | One-sentence explanation derived from `_explain_violation`.                             |
| `recommended_action` | string           | One-sentence remediation hint derived from `_explain_violation`.                        |
| `matched_paths`      | array of strings | The input paths that triggered this rule.                                               |
| `matched_commands`   | array of strings | The input commands that satisfied a `require_command` rule. Empty when none.            |
| `matched_claims`     | array of strings | The input claims that satisfied a `require_claim` rule. Empty when none.                |
| `required_paths`     | array of strings | The patterns the rule requires (`before_paths` or `when_paths`, depending on kind).     |
| `required_commands`  | array of strings | The commands the rule requires, for `require_command`.                                  |
| `required_claims`    | array of strings | The claims the rule requires, for `require_claim` (see CLDC-0004).                      |
| `source_path`        | string \| null   | Provenance: which source produced the rule.                                             |
| `source_block_id`    | string \| null   | Provenance: inline block or preset block id.                                            |

The list contains 14 keys in total. All array fields are always
present; empty arrays are written as `[]`, never omitted.

### Git metadata

When `cldc ci` produces the report, the renderer attaches a `git`
object. The shape is normalized in `_normalize_git` in
`src/cldc/runtime/reporting.py`:

| Key                | Type              | Notes                                                       |
|--------------------|-------------------|-------------------------------------------------------------|
| `mode`             | string            | The collection mode (e.g. `staged` or `range`).             |
| `write_path_count` | integer           | Number of paths derived from git, after normalization.      |
| `base`             | string (optional) | Present for range mode.                                     |
| `head`             | string (optional) | Present for range mode.                                     |
| `git_command`      | array (optional)  | The exact `git` argv used, for reproducibility.             |

The `git` key is **omitted** entirely from reports produced by
`cldc check`. Consumers must treat it as optional.

### Exit codes

`cldc check` and `cldc ci` map `decision` directly to a process exit
code in `src/cldc/cli/main.py`:

| Decision | Exit code |
|----------|-----------|
| `pass`   | `0`       |
| `warn`   | `0`       |
| `block`  | `2`       |

Any uncaught exception in the loader, parser, or evaluator returns
exit code `1`. Argparse usage errors return whatever argparse decides,
typically `2`. Consumers may rely on `0` / `2` to mean "report was
produced successfully" and on `1` to mean "no report was produced".

## Compatibility

A consumer at this `$schema` URL **must**:

- Reject the report when `$schema` is present and not equal to
  `CHECK_REPORT_SCHEMA`.
- Reject the report when `format_version` is present and not equal to
  `CHECK_REPORT_FORMAT_VERSION`.
- Treat all 14 violation fields as required for freshly emitted reports
  and never omit array fields when re-serializing.
- Preserve the `git` block byte-for-byte when re-serializing a report
  that contains it.

### Legacy unversioned reports

For backward compatibility with reports produced before this RFC was
frozen, `load_check_report` in `src/cldc/runtime/reporting.py` accepts
payloads that omit `$schema` and `format_version` entirely, as long as
every other required field is present and well-typed. The loader
re-stamps such reports with the current `$schema` and `format_version`
on load. This back-compat path is locked in by
`test_cli_explain_command_accepts_legacy_unversioned_saved_report` in
`tests/test_cli.py` and is the only allowed way to produce a payload
without those two keys. Any future change that drops this fallback
requires a new `$schema` URL and a superseding RFC.

## Validation

Test surface that locks in this contract today:

- `tests/test_runtime.py` — evaluation outcomes for every rule kind,
  decision computation, blocking-count math.
- `tests/test_cli.py` — CLI exit-code mapping, JSON output shape,
  legacy-unversioned acceptance, `cldc explain` re-rendering.

## Reference

- `src/cldc/runtime/report_schema.py` — schema constants.
- `src/cldc/runtime/evaluator.py` — `Violation`, `CheckReport`,
  `check_repo_policy`, `_explain_violation`, `_summarize_report`.
- `src/cldc/runtime/reporting.py` — `load_check_report`,
  `_normalize_violation`, `_normalize_git`, `render_check_report`.
- `src/cldc/cli/main.py` — exit-code mapping for `check` and `ci`.

## Appendix: minimal valid example

Abbreviated output of `cldc check tests/fixtures/repo_a --write src/main.py --json`:

```json
{
  "$schema": "https://cldc.dev/schemas/policy-report/v1",
  "format_version": "1",
  "ok": true,
  "repo_root": "/abs/path/to/repo",
  "lockfile_path": ".claude/policy.lock.json",
  "decision": "warn",
  "default_mode": "warn",
  "summary": "Policy check found 1 non-blocking violation(s).",
  "next_action": "Read at least one path matching docs/rfcs/** before modifying src/main.py.",
  "inputs": {
    "read_paths": [],
    "write_paths": ["src/main.py"],
    "commands": [],
    "claims": []
  },
  "violation_count": 1,
  "blocking_violation_count": 0,
  "violations": [
    {
      "rule_id": "must-read-rfc",
      "kind": "require_read",
      "mode": "warn",
      "message": "Read the RFCs before touching source.",
      "explanation": "Write activity src/main.py triggered require_read rule 'must-read-rfc', but no required read matched docs/rfcs/**.",
      "recommended_action": "Read at least one path matching docs/rfcs/** before modifying src/main.py.",
      "matched_paths": ["src/main.py"],
      "matched_commands": [],
      "matched_claims": [],
      "required_paths": ["docs/rfcs/**"],
      "required_commands": [],
      "required_claims": [],
      "source_path": ".claude-compiler.yaml",
      "source_block_id": null
    }
  ]
}
```
