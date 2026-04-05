# 2026-04-04 claude-md-compiler cron log

## Iteration 1 — SHIPPING FEATURES
- **What changed**
  - Added canonical repo discovery that walks up from nested paths and recognizes both `.claude-compiler.yaml` and `.claude-compiler.yml`.
  - Enriched source loading with discovery metadata and explicit source precedence ordering.
  - Hardened YAML/rule validation with contextual errors and kind-specific required field checks.
  - Expanded compiler output with schema metadata, source counts, and discovery details.
  - Shipped a new `cldc doctor` command for discovery/validation diagnostics and stale lockfile detection.
  - Updated README current-status text to match the implemented CLI.
- **Verification run**
  - `python -m pytest -q` → `17 passed`
  - `PYTHONPATH=src python -m cldc.cli.main doctor . --json` → success
  - `PYTHONPATH=src python -m cldc.cli.main compile . --json` → success
- **Current state of project**
  - Commit shipped on `main` with message `feat: add policy discovery and doctor command`.
  - The repo now has a real compile+doctor workflow with deterministic lockfile metadata and much better operator visibility.
  - Policy discovery works from nested paths instead of requiring callers to start at the exact repo root.
  - Validation coverage now includes config variants, missing kind-specific fields, nested discovery, doctor health output, and stale lockfile warnings.
  - Core runtime enforcement (`check` / evaluation engine) is still the biggest missing MVP gap.
- **Next highest-leverage task**
  - Implement the first end-to-end `cldc check` runtime slice: load compiled policy, evaluate touched paths and executed commands against `deny_write`, `require_read`, and `require_command`, and return machine-readable violations with mode-aware exit codes.

## Iteration 2 — QUALITY / POLISH / PRODUCTION-GRADE
- **What changed**
  - Hardened `cldc doctor` so it now validates existing lockfiles for malformed JSON, schema drift, format-version drift, repo-root mismatches, and rule-count mismatches instead of only checking presence + staleness.
  - Added a single machine-readable `next_action` recommendation to doctor output so operators get one concrete remediation step instead of vague diagnostics.
  - Enriched compile JSON output with `default_mode`, source provenance, discovery metadata, and warnings to make compile artifacts easier to inspect in CI and automation.
  - Added JSON-formatted CLI failure payloads for `--json` mode so automation gets stable error details on invalid policy input.
  - Expanded README usage guidance to cover editable install + doctor/compile workflow and documented the stronger doctor guarantees.
- **Verification run**
  - `python -m pytest -q` → `20 passed`
  - `cldc doctor .` → success, shows lockfile metadata + recommended next action
  - `cldc doctor . --json` → success, includes `lockfile_schema`, `lockfile_format_version`, and `next_action`
  - `cldc compile . --json` → success, includes `default_mode`, `source_paths`, `discovery`, and `warnings`
- **Current state of project**
  - The compile/doctor slice is now more production-grade for local + CI usage because it can detect corrupted or drifted lockfiles before enforcement exists.
  - JSON outputs are more explainable and better suited for downstream automation, while human doctor output now points to a single recommended remediation.
  - Test coverage grew from 17 to 20 passing tests, including malformed lockfile handling, schema drift detection, and JSON CLI error reporting.
  - Core runtime enforcement (`cldc check`) remains the biggest MVP gap, but the artifacts and diagnostics around it are more trustworthy.
- **Next highest-leverage task**
  - Implement `cldc check` MVP: load `.claude/policy.lock.json`, accept touched-path / executed-command inputs, evaluate `deny_write`, `require_read`, and `require_command`, and emit machine-readable violations with mode-aware exit codes.

## Iteration 3 — SHIPPING FEATURES
- **What changed**
  - Shipped an MVP `cldc check` command that loads the compiled lockfile and evaluates runtime evidence from `--read`, `--write`, and `--command` inputs.
  - Added the first runtime evaluator under `src/cldc/runtime/` with deterministic handling for `deny_write`, `require_read`, and `require_command` rules plus structured violation objects.
  - Implemented mode-aware enforcement decisions so `warn`/`observe` violations stay non-blocking while `block`/`fix` violations return exit code `2` for CI and automation.
  - Added stable JSON and human-readable check output including matched paths, required reads/commands, rule provenance, and aggregate decision metadata.
  - Updated the fixture policy and README so the repo now demonstrates both warning-level guidance and a true blocking rule.
- **Verification run**
  - `python -m pytest -q` → `27 passed`
  - `PYTHONPATH=src python -m cldc.cli.main check tests/fixtures/repo_a --write src/main.py --json` → success, returns two warning-level violations (`must-read-rfc`, `run-tests`)
  - `PYTHONPATH=src python -m cldc.cli.main check tests/fixtures/repo_a --write generated/output.json --json` → exit code `2`, returns one blocking violation (`generated-lock`)
- **Current state of project**
  - The repo now has an end-to-end compile → check enforcement loop instead of only artifact generation and diagnostics.
  - Operators and CI can feed explicit runtime evidence into `cldc check` and get deterministic machine-readable violations with rule-level provenance.
  - The shippable MVP now covers the three core rule kinds most directly tied to repo safety and workflow enforcement.
  - A repo-local `venv/` is not present here, so verification used the available Python 3.11 interpreter directly rather than `source venv/bin/activate`.
  - Commit shipped on `main` with message `feat: add runtime policy check command`.
- **Next highest-leverage task**
  - Expand runtime inputs beyond explicit CLI flags by adding stdin/JSON event ingestion (or a CI-focused wrapper command) so real agent transcripts and automation can feed `cldc check` without manual argument repetition.

## Iteration 4 — QUALITY / POLISH / PRODUCTION-GRADE
- **What changed**
  - Fixed a production-grade enforcement gap where absolute paths silently bypassed policy checks; `cldc check` now canonicalizes both repo-relative and absolute in-repo paths before glob matching.
  - Hardened `cldc check` to reject escaped/out-of-repo paths and to fail fast on schema drift, format drift, repo-root mismatch, embedded rule-count mismatch, and stale lockfiles instead of trusting outdated artifacts.
  - Improved CLI/operator ergonomics with `cldc --version`, richer command descriptions, explicit `--json` help text, and README guidance that now documents absolute-path support and stale-lockfile refusal.
  - Expanded runtime + CLI tests to cover absolute-path normalization, out-of-repo path rejection, stale lockfile rejection, schema drift rejection, and version/help visibility.
- **Verification run**
  - `python -m pytest -q` → `33 passed`
  - `python -m pip install -e .` → success
  - `cldc --version` → success (`cldc 0.1.0`)
  - `cldc check tests/fixtures/repo_a --write $(pwd)/tests/fixtures/repo_a/src/main.py --json` → success, normalizes the absolute path to `src/main.py` and returns the expected warning-level violations
- **Current state of project**
  - Runtime enforcement is materially more trustworthy because real absolute-path evidence from shells/CI now hits the same policy rules as repo-relative inputs.
  - `cldc check` will no longer silently evaluate against drifted or stale policy artifacts, reducing the chance of false confidence in CI.
  - Installability remains clean via editable install, and the CLI surface is easier for operators to discover and script correctly.
  - The repo now has 33 passing tests covering both happy-path enforcement and key failure modes around stale/drifted artifacts.
- **Next highest-leverage task**
  - Add a CI-friendly event ingestion path for `cldc check` (stdin / JSON payloads or a wrapper command) so real agent transcripts and automation can feed evidence without repetitive flag expansion.

## Iteration 5 — SHIPPING FEATURES
- **What changed**
  - Added a canonical runtime execution-input model in `src/cldc/runtime/events.py` that loads machine-readable JSON payloads from files or stdin, supports both top-level batch lists and per-event records, and validates malformed evidence with explicit errors.
  - Extended `cldc check` with `--events-file` and `--stdin-json` so CI jobs and agent wrappers can feed read/write/command/claim evidence without repeating many CLI flags.
  - Wired event payload merging into runtime evaluation so explicit flags and JSON evidence compose cleanly, with normalized `claims` now preserved in the machine-readable report for downstream automation.
  - Updated human CLI output and README usage examples to document the new event-ingestion flow and payload shape.
  - Expanded runtime + CLI coverage for event batches, stdin ingestion, file ingestion, malformed payload rejection, and merged explicit/event inputs.
- **Verification run**
  - `python -m pytest -q` → `39 passed`
  - `python -m pip install -e .` → success
  - `printf '%s' '{"events":[{"kind":"read","path":"docs/rfcs/CLDC-0006-validator-engine.md"},{"kind":"write","path":"src/main.py"},{"kind":"command","command":"pytest -q"},{"kind":"claim","claim":"qa-reviewed"}]}' | cldc check <tmp-repo> --stdin-json --json` → success, decision `pass`
  - `cldc check <tmp-repo> --events-file <(printf '%s' '{"write_paths":["generated/output.json"]}') --json` → exit code `2`, blocking `generated-lock` violation
- **Current state of project**
  - The repo now has a real machine-readable ingestion path for runtime evidence, which closes the most obvious usability gap between the MVP checker and actual CI/agent workflows.
  - `cldc check` can now evaluate explicit flags, stdin JSON, and file-based JSON in one run without losing deterministic normalization or stale-lockfile protections.
  - Claims are not enforced yet, but they are now part of the canonical event payload/report contract so future explain/fix/CI flows have a stable place to hang completion assertions.
  - Test coverage grew from 33 to 39 passing tests, with direct coverage of the new event schema and CLI ingestion modes.
- **Next highest-leverage task**
  - Ship the first dedicated `cldc ci` workflow that derives changed files from git (`--staged` and/or `--base`/`--head`) and feeds them into `cldc check`, turning the current policy engine into a one-command CI entrypoint.

## Iteration 6 — QUALITY / POLISH / PRODUCTION-GRADE
- **What changed**
  - Hardened lockfile freshness validation by adding a deterministic `source_digest` fingerprint over the canonical policy source bundle and embedding it in compiled lockfiles + compile JSON output.
  - Taught both `cldc doctor` and `cldc check` to detect content drift even when timestamps and rule counts are misleading, closing a real false-trust gap in CI and local enforcement.
  - Enriched doctor output with current + lockfile source digests so operators can see exactly which artifact identity they are comparing.
  - Expanded regression coverage for digest emission, digest-aware doctor metadata, and drift cases where policy content changes but lockfile mtimes are intentionally backdated.
  - Updated README shipping guidance to document source-digest enforcement and the stronger stale-lockfile guarantees.
- **Verification run**
  - `python -m pytest -q` → `41 passed`
  - `python -m pip install -e .` → success
  - `python -m build` → success (sdist + wheel)
  - `cldc compile <tmp-repo> --json` → success, includes `source_digest`
  - `cldc doctor <tmp-repo> --json` → success, includes both `source_digest` and `lockfile_source_digest`
  - `cldc check <tmp-repo> --write generated/output.json --json` after backdated policy-content drift → exit code `1`, JSON error `compiled lockfile source_digest does not match the current policy sources; re-run \`cldc compile\``
- **Current state of project**
  - The lockfile is now materially harder to trust incorrectly: timestamp-only freshness checks are no longer the sole guardrail.
  - Packaging verification now covers editable install plus wheel/sdist generation, which improves release readiness for the current CLI slice.
  - Test coverage grew from 39 to 41 passing tests, including a direct regression for content drift with preserved rule count and older source mtimes.
  - The repo still lacks the dedicated `cldc ci` command, but the underlying checker is more trustworthy for that next integration step.
- **Next highest-leverage task**
  - Ship `cldc ci` as the first one-command git-aware entrypoint (`--staged`, `--base`, `--head`) that derives changed files from git, feeds them into `cldc check`, and preserves the current JSON/error contracts for CI automation.

## Iteration 7 — SHIPPING FEATURES
- **What changed**
  - Shipped a new `cldc ci` command that derives write paths directly from git and then evaluates them through the existing compiled policy engine.
  - Added explicit git selection modes for CI/prod usage: `--staged` for `git diff --cached --name-only` and `--base`/`--head` for PR-style range diffs.
  - Preserved the current `cldc check` decision/violation JSON contract while appending git provenance metadata so automation can tell which diff source was enforced.
  - Added a dedicated runtime git integration module plus regression coverage for staged diffs, base/head diffs, and malformed selector usage.
  - Updated README usage/status docs so the project now documents a true one-command CI entrypoint instead of only manual `cldc check` invocation.
- **Verification run**
  - `python -m pytest -q` → `47 passed`
  - `python -m pip install -e .` → success
  - `python -m build` → success (sdist + wheel)
  - `cldc ci <tmp-repo> --staged --json` → success, returns git metadata plus the expected warning-level violations for `src/main.py`
- **Current state of project**
  - The repo now has a real git-aware enforcement entrypoint instead of requiring callers to expand changed files into repeated `--write` flags by hand.
  - CI wrappers can evaluate staged changes or PR ranges with explicit provenance and the same violation semantics already proven by `cldc check`.
  - Test coverage grew from 41 to 47 passing tests, including direct runtime and CLI coverage for git-derived write-path collection.
  - The end-to-end story is materially more useful for local hooks and CI pipelines because policy enforcement can now start from git state, not just ad hoc manual inputs.
  - Commit shipped on `main` with message `feat: add git-aware ci policy command`.
- **Next highest-leverage task**
  - Ship the first `cldc explain` / explainability report slice so CI and local runs can turn raw violations into reviewer-friendly rationale, provenance, and recommended next actions without losing the stable JSON artifact model.

## Iteration 8 — QUALITY / POLISH / PRODUCTION-GRADE
- **What changed**
  - Added the first explainability/polish slice to runtime reports: every `cldc check` / `cldc ci` result now includes a deterministic top-level `summary` plus a single `next_action` recommendation.
  - Enriched each violation object with `explanation` and `recommended_action` fields so JSON consumers no longer need to reverse-engineer why a rule fired from raw rule metadata alone.
  - Upgraded human-readable CLI output to print the aggregate summary, the recommended next action, and per-violation “why” / “next step” guidance while preserving the existing decision semantics and exit codes.
  - Expanded runtime + CLI regression coverage for pass/warn/block explainability contracts and documented the stronger output guarantees in `README.md`.
  - Verified the new explainability contract through both direct `cldc check` runs and git-aware `cldc ci` runs using disposable temp repos so tracked fixtures stay clean.
- **Verification run**
  - `python -m pytest -q` → `48 passed`
  - `python -m pip install -e .` → success
  - `python -m build` → success (sdist + wheel)
  - `cldc check <tmp-repo> --write src/main.py --json` → success, now includes `summary`, `next_action`, and per-violation `explanation` / `recommended_action`
  - `cldc ci <tmp-repo> --base HEAD --head HEAD --json` → success, returns the same explainability fields with `git` provenance and zero-change `pass` output
- **Current state of project**
  - The policy checker is more production-grade for humans and automation because outputs now directly answer what happened and what to do next instead of only surfacing low-level rule matches.
  - The new JSON fields are deterministic and append-only, so downstream CI/reporting integrations can adopt them without losing the stable decision/violation contract already in place.
  - Human CLI output is much more reviewer-friendly, which reduces operator friction even before a standalone `cldc explain` command exists.
  - Test coverage grew from 47 to 48 passing tests, with dedicated assertions for explainability behavior across pass, warn, and block paths.
- **Next highest-leverage task**
  - Ship a dedicated `cldc explain` command that can render or export the new report model from existing lockfile + evidence artifacts, rather than only surfacing explainability inline during `check` / `ci` execution.
