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
