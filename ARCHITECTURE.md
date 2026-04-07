# Architecture

## System Overview

`cldc` is a local-first policy compiler and enforcement CLI. Its core job is to turn repository instructions into explicit, versioned artifacts and then evaluate runtime evidence against those artifacts without hidden heuristics.

The system has two layers:

- Core: ingestion, parsing, compilation, evaluation, report validation, fix-plan synthesis.
- Shell: CLI parsing, file output, and git integration.

## Data Flow

1. Discovery
   `discover_policy_repo()` walks up from any nested path until it finds a policy-bearing repo.
2. Ingestion
   `load_policy_sources()` reads `CLAUDE.md`, inline `cldc` blocks, compiler config, and policy fragments into canonical `PolicySource` records.
3. Parsing
   `parse_rule_documents()` validates rule structure, normalizes modes and fields, and rejects duplicate IDs.
4. Compilation
   `compile_repo_policy()` writes `.claude/policy.lock.json` with schema/version metadata and a deterministic source digest.
5. Evaluation
   `check_repo_policy()` loads the compiled lockfile, validates freshness against current sources, normalizes runtime evidence, and emits a `CheckReport`.
6. Rendering
   `render_check_report()` and `render_fix_plan()` turn saved artifacts into text or Markdown without rerunning enforcement.

## Module Map

- `src/cldc/ingest/discovery.py`
  Finds the repo root, candidate config files, policy fragments, and lockfile presence.
- `src/cldc/ingest/source_loader.py`
  Loads source contents, extracts inline fenced blocks, and validates repo-local include patterns.
- `src/cldc/parser/rule_parser.py`
  Defines the normalized rule model and validates the supported rule DSL.
- `src/cldc/compiler/policy_compiler.py`
  Builds the lockfile and produces `doctor` diagnostics over discovery, parsing, and lockfile state.
- `src/cldc/runtime/evaluator.py`
  Evaluates evidence against the compiled rules and produces a versioned report artifact.
- `src/cldc/runtime/events.py`
  Validates file-based and stdin JSON evidence payloads.
- `src/cldc/runtime/git.py`
  Collects changed paths from staged state or a base/head range.
- `src/cldc/runtime/reporting.py`
  Validates saved policy reports and renders explanations.
- `src/cldc/runtime/remediation.py`
  Turns policy reports into deterministic remediation plans.
- `src/cldc/cli/main.py`
  Exposes the CLI and keeps exit-code behavior stable.

## Supported Semantics

Current runtime enforcement supports:

- `deny_write`
- `require_read`
- `require_command`
- `couple_change`

Current non-enforced but accepted evidence:

- `claim` events are preserved in the report model but do not affect decisions.

## Invariants

- Policy sources are loaded in deterministic order.
- Lockfiles, reports, and fix plans carry explicit schema/version markers.
- A stale or schema-drifted lockfile is an error, not a warning-only best effort.
- Unsupported rule kinds in compiled artifacts are explicit failures, not silent no-ops.
- Include patterns from config must stay within the repo root.
- Runtime path normalization rejects paths that escape the discovered repo root.

## Failure Model

Expected operator failures:

- malformed YAML or JSON
- duplicate rule IDs
- missing compiled lockfile
- stale lockfile after policy edits
- lockfile schema/version drift
- git invocation failure in `cldc ci`

`doctor` is the first-line diagnosis tool. Use it before debugging enforcement behavior.

## Operator Runbook

When policy sources change:

1. Run `uv run cldc compile .`
2. Commit the updated `.claude/policy.lock.json`
3. Run `uv run pytest -q`

When CI or local enforcement fails unexpectedly:

1. Run `uv run cldc doctor . --json`
2. If the lockfile is stale or drifted, re-run `uv run cldc compile .`
3. Re-run `uv run cldc check ...` or `uv run cldc ci ...`
4. If you need a human-readable handoff, render the saved report with `uv run cldc explain ...`

## Known Gaps

- no repo topology scanner yet
- no preset policy packs
- no claim enforcement
- no automatic fix execution
- no built-in lint/type/coverage gate in CI
