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
