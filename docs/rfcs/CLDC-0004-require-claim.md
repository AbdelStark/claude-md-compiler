# CLDC-0004: `require_claim` rule

- **Status**: Frozen
- **Created**: 2026-04-07
- **Supersedes**: —
- **Superseded by**: —

## Abstract

The `require_claim` rule kind expresses a path-scoped sign-off
requirement: "any write under these paths must be accompanied by at
least one of these named claims." Claims are opaque strings agreed
upon between the policy author and whatever upstream workflow asserts
them. This RFC freezes the rule shape, the claim ingestion surfaces,
and the way violations and remediations expose claim state.

## Motivation

Some workflows can't be enforced by inspecting paths and commands
alone. "QA reviewed this," "the release captain signed off," "CI is
green on the merge commit" — these are facts about the world, not
about the working tree. `require_claim` lets a policy require that one
of those facts be asserted before a write is allowed. The rule is
intentionally narrow: claims are strings, equality is the only
comparison, and `cldc` does not try to verify the truth of any claim.

## Specification

### Rule shape

A `require_claim` rule is a rule (CLDC-0001) whose `kind` is
`require_claim` and whose required fields are `claims` and
`when_paths`. The full schema is:

| Field             | Type             | Required                | Notes                                                          |
|-------------------|------------------|-------------------------|----------------------------------------------------------------|
| `id`              | string           | yes                     | Unique across the lockfile.                                    |
| `kind`            | string           | yes                     | Must equal `"require_claim"`.                                  |
| `message`         | string           | yes                     | Human-readable description.                                    |
| `mode`            | string \| null   | no                      | Falls back to `default_mode` if omitted.                       |
| `claims`          | array of strings | yes                     | Non-empty. Each claim is a non-empty string.                   |
| `when_paths`      | array of strings | yes                     | Non-empty. Glob patterns; matched with `fnmatch.fnmatchcase`.  |
| `paths`           | n/a              | no (must be omitted)    | Not used by this kind.                                         |
| `before_paths`    | n/a              | no (must be omitted)    | Not used by this kind.                                         |
| `commands`        | n/a              | no (must be omitted)    | Not used by this kind.                                         |
| `source_path`     | string \| null   | no                      | Provenance.                                                    |
| `source_block_id` | string \| null   | no                      | Provenance.                                                    |

The required-field matrix is encoded in `REQUIRED_FIELDS_BY_KIND` in
`src/cldc/parser/rule_parser.py`. A rule that omits `claims` or
`when_paths` is rejected at parse time.

### Evaluation semantics

The evaluator (`_evaluate_rule` in `src/cldc/runtime/evaluator.py`)
applies a `require_claim` rule as follows:

1. Compute `triggered_paths` = the subset of normalized `write_paths`
   that match any pattern in `when_paths`.
2. If `triggered_paths` is empty, the rule does not fire. There is no
   violation regardless of which claims were asserted.
3. Otherwise, compute `matched_claims` = the subset of normalized
   input claims that appear in the rule's `claims` list. Comparison is
   exact string equality after stripping leading/trailing whitespace.
4. If `matched_claims` is non-empty, the rule is satisfied.
5. Otherwise, the rule produces one violation whose `matched_paths`
   are the `triggered_paths`, whose `matched_claims` is `[]`, and
   whose `required_claims` is the rule's `claims` list.

The rule is **path-scoped**: it only fires for write activity. Reads,
commands, and claims with no matching write are inert. This is the
same shape as `require_command`, just keyed on claims instead of
commands.

### Claim ingestion surfaces

Claims can reach the evaluator through any of four surfaces. They are
deduplicated by string equality and normalized by stripping
whitespace. Their order does not matter.

1. **`--claim <name>` CLI flag**, repeatable. Wired in
   `_add_runtime_input_flags` in `src/cldc/cli/main.py`. Available on
   `cldc check`, `cldc ci`, `cldc explain`, and `cldc fix`.
2. **`--events-file <path>`**: a JSON file whose top-level shape is
   accepted by `load_execution_inputs` in
   `src/cldc/runtime/events.py`. Either a top-level `claims` array of
   strings or an `events` array of `{kind: "claim", claim: "<name>"}`
   objects (or both) is honored.
3. **`--stdin-json`**: the same JSON shape, read from standard input
   instead of a file, validated by `load_execution_inputs_text`.
4. **Programmatic event payload**: `check_repo_policy(...,
   event_payload=...)` accepts the same JSON shape directly. Used by
   embedding callers.

The four surfaces are merged. A claim asserted via any one of them
satisfies a rule that lists it.

### Violation and remediation shape additions

Every check report (CLDC-0002) violation already exposes
`matched_claims` and `required_claims`. For non-claim rule kinds these
are always `[]`. For `require_claim`, `required_claims` is the rule's
`claims` list and `matched_claims` is the asserted claims that
satisfied the rule (which is always `[]` when the rule produced a
violation).

Every fix plan (CLDC-0003) remediation exposes `suggested_claims`. For
non-claim rule kinds this is always `[]`. For `require_claim`, it is
the deduped `required_claims` from the source violation.

## Compatibility

A consumer at the policy lockfile schema **must**:

- Parse a `require_claim` rule with the field set above.
- Refuse to load a `require_claim` rule that omits `claims` or
  `when_paths`, or whose `claims` is empty.
- Always populate `matched_claims` and `required_claims` in violation
  output, even when empty.
- Always populate `suggested_claims` in fix-plan output, even when
  empty.

A consumer that does not understand the `require_claim` kind itself
must reject the lockfile rather than skip the rule. This is enforced
by `_evaluate_rule`, which raises `ValueError` on any unknown kind.

### Forward compatibility

Adding new claim ingestion surfaces is a non-breaking change: the
union of surfaces still produces the same `claims` list. Removing or
renaming an existing surface is a breaking change and requires a
superseding RFC. Changing claim equality semantics (case folding,
namespacing, structured claim payloads) is also a breaking change.

## Validation

Test surface that locks in this contract today:

- `tests/test_rule_parser.py` — required-field validation for
  `require_claim`.
- `tests/test_runtime.py` — evaluation semantics, ingestion via every
  surface, violation shape.
- `tests/test_cli.py` — CLI flag plumbing for `--claim`,
  `--events-file`, and `--stdin-json`.

## Reference

- `src/cldc/parser/rule_parser.py` — `ALLOWED_RULE_KINDS`,
  `REQUIRED_FIELDS_BY_KIND`, `_validate_rule_item`.
- `src/cldc/runtime/evaluator.py` — `_evaluate_rule`,
  `_matching_claims`, `_explain_violation`, `_build_violation`.
- `src/cldc/runtime/events.py` — `ALLOWED_EVENT_KINDS`,
  `ExecutionInputs`, `load_execution_inputs`,
  `load_execution_inputs_file`, `load_execution_inputs_text`.
- `src/cldc/cli/main.py` — `_add_runtime_input_flags`.
- `src/cldc/runtime/remediation.py` — `_suggested_claims`.

## Appendix: example rule and violation

Rule, as it would appear in a policy fragment:

```yaml
rules:
  - id: ship-only-when-ci-green
    kind: require_claim
    mode: block
    when_paths:
      - "src/**"
    claims:
      - "ci-green"
    message: Require a `ci-green` claim to ship source changes under src/**.
```

Violation, as it would appear in a check report when `src/main.py`
was written without asserting any claim:

```json
{
  "rule_id": "ship-only-when-ci-green",
  "kind": "require_claim",
  "mode": "block",
  "message": "Require a `ci-green` claim to ship source changes under src/**.",
  "explanation": "Write activity src/main.py triggered require_claim rule 'ship-only-when-ci-green', but no required claim matched ci-green.",
  "recommended_action": "Record one of the required claims before finishing: ci-green.",
  "matched_paths": ["src/main.py"],
  "matched_commands": [],
  "matched_claims": [],
  "required_paths": [],
  "required_commands": [],
  "required_claims": ["ci-green"],
  "source_path": "policies/release.yml",
  "source_block_id": null
}
```
