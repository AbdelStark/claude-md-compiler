# Changelog

All notable changes to `claude-md-compiler` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New `forbid_command` rule kind — the inverse of `require_command`.
  Fires when any of the listed `commands` is observed in the runtime
  evidence and, if `when_paths` is specified, any write path matches
  one of those patterns. Wired through parser, lockfile compiler,
  evaluator, explain, fix plan, and CLI renders. The bundled `strict`
  preset now ships a `preset-strict-forbid-raw-pip-install` rule that
  blocks `pip install` against `pyproject.toml` edits so teams on
  `uv`/`poetry`/`pip-tools` stay on their canonical installer.
- Fix-plan remediations gained a `forbidden_commands` field carrying
  the observed-and-forbidden command list so text/markdown renders can
  call them out explicitly. Additive only — existing consumers that do
  not inspect the new field continue to parse correctly.
- `cldc check` text output now prints `matched commands` per violation
  so forbid_command firings are self-explanatory without needing
  `cldc explain`.
- End-to-end test suite under `tests/e2e/` that clones
  `langchain-ai/langchain`, drops a hand-authored `.claude-compiler.yaml`
  (`tests/e2e/compiler.yaml`) translating langchain's CLAUDE.md prose
  into enforceable cldc rules, and walks the full compile → check → fix
  flow with red/green coverage. Marked `@pytest.mark.e2e` and excluded
  from the default pytest run; opt-in via `make e2e` or
  `uv run pytest -m e2e`. 9 tests, ~10s wall time including the shallow
  clone.
- `e2e` pytest marker registered in `[tool.pytest.ini_options].markers`
  and excluded from `addopts` so the default suite stays fast.
- `make e2e` Makefile target.
- The bundled `default` preset's `preset-default-generated-read-only`
  rule now also blocks `**/dist/**`, `**/build/**`, and `**/generated/**`
  in addition to the top-level paths. The lockfile-sync `require_command`
  rule now also matches `**/pyproject.toml`, `**/package.json`, etc.
  This makes the preset usable in monorepos (each package keeps its own
  dist/ and pyproject.toml).
- `cldc tui` — interactive Textual-based terminal UI. Launches a three-pane
  policy explorer (sources / rules / detail) with a four-field evidence
  form and a colored decision panel. Keybindings: `c` compile, `r` run
  check, `d` doctor, `p` presets, `R` reload, `ctrl+l` clear evidence,
  `?` help, `q` quit.
- `textual>=0.80` added as a runtime dependency.
- `pytest-asyncio` added to dev deps; enabled in `addopts` with
  `asyncio_mode = "auto"` so `async def test_*` drivers work transparently.
- `tests/test_tui.py` with Pilot-based smoke tests for the state module,
  the reactive app mount, and the compile/run-check/clear-evidence bindings.
- `GitError` exception class in `cldc.errors` for git-related failures
  surfaced by `cldc ci`. Inherits from `CldcError` → `ValueError`, so
  existing `except ValueError` consumers keep working.
- `--json` error payloads now include `error_type` (the exception class
  name) so machine consumers can branch without regex-parsing the message.
- `--verbose` now prints the full traceback on errors (text and JSON
  modes). Without `--verbose` the CLI still emits a single-line message.
- `.pre-commit-config.yaml` with ruff lint + format, trailing-whitespace,
  EOF-fixer, YAML/TOML syntax, large-file, and merge-conflict checks.
  Install with `uvx pre-commit install`.

### Changed

- `discover_policy_repo` now raises `FileNotFoundError` with an actionable
  message (`"Repo path not found: <path> — pass an existing directory…"`)
  instead of just the raw path. Every CLI command surfaces this
  improved error.
- `src/cldc/runtime/git.py` now raises typed `GitError` instead of raw
  `ValueError` for invalid flag combinations, git command failures, and
  missing git binary on PATH. The flag-validation order was also swapped
  so `--head` without `--base` is reported as "cannot use --head without
  --base" instead of the less-specific "requires either --staged or
  --base" message.

### Fixed

- `doctor_repo_policy` no longer crashes on repos that extend a bundled
  preset. The staleness check now skips sources whose path starts with
  `preset:`, mirroring the fix already landed in
  `runtime/evaluator.py::_validate_lockfile_freshness`.
- 100% docstring coverage on every public, non-TUI class and function in
  `src/cldc/` (up from ~52%). All `to_dict` methods, `ExecutionInputs.merged_with`,
  `load_check_report_file`, and `load_check_report_text` now have a
  documented contract.

## [0.1.1] - 2026-04-07

### Added

- `require_claim` rule kind: writes matching `when_paths` are blocked unless
  one of the listed `claims` is asserted via `--claim`, `--events-file`,
  `--stdin-json`, or an event payload of kind `claim`. Claims were previously
  ingested but never enforced, so this closes a real bypass.
- `--claim` CLI flag on `check`, `ci`, `explain`, and `fix`. The flag is
  repeatable; each invocation adds one asserted claim to the runtime evidence
  set before evaluation.
- Bundled preset policy packs under `src/cldc/presets/packs/`:
  - `default` blocks generated writes and warns on manifests touched without
    a paired lockfile sync.
  - `strict` enforces tests-follow-source coupling, architecture reads, and a
    `ci-green` claim before merging.
  - `docs-sync` couples public surface changes with README and docs updates.
- `cldc preset list` and `cldc preset show NAME` subcommands for inspecting
  bundled packs without leaving the CLI.
- `extends:` directive in `.claude-compiler.yaml` that merges named bundled
  presets into the compiled lockfile alongside repo-local rules. Conflicts
  are surfaced as parser errors rather than silently overridden.
- `matched_claims` and `required_claims` fields on violations and
  `suggested_claims` on fix-plan remediations, so explainable output and
  remediation can both reason about claim state.
- New `preset` source kind in `SOURCE_PRECEDENCE`, exported as
  `PRESET_SOURCE_KIND` from `cldc.presets`.
- Typed exception hierarchy in `cldc.errors` (`CldcError`, `LockfileError`,
  `RuleValidationError`, `EvidenceError`, `ReportError`, `PolicySourceError`,
  `PresetError`, `PresetNotFoundError`, `RepoBoundaryError`). Every class
  inherits from `ValueError` for back-compat.
- Structured logging via `cldc._logging`. Library is silent by default
  (NullHandler). CLI exposes `--verbose`/`-v` and `--quiet`/`-q` to attach
  stderr handlers.
- `py.typed` marker so downstream type checkers pick up inline annotations.
- Bundled dev toolchain via `[dependency-groups].dev`: `ruff`, `pyright`,
  `pytest-cov`, `pytest-benchmark`, `hypothesis`, `types-PyYAML`.
- `[tool.ruff]`, `[tool.pyright]`, `[tool.coverage.*]` config in
  `pyproject.toml`.
- CI jobs for lint (`ruff check`, `ruff format --check`), typecheck
  (`pyright src`), and coverage (`pytest --cov --cov-fail-under=80`).
- Hypothesis property tests (`tests/test_properties.py`, 16 tests across 6
  classes covering path normalization, glob matching, rule evaluation, and
  evidence loader idempotence).
- `pytest-benchmark` baselines (`tests/test_benchmarks.py`, 6 benchmarks
  opt-in via `--benchmark-only`; skipped by default via `--benchmark-skip` in
  `addopts`).
- `ARCHITECTURE.md` documenting the layered design, data flow, schema
  contracts, invariants, and extension points.
- `docs/rfcs/` with 6 frozen RFCs (`CLDC-0001` through `CLDC-0005`, plus an
  index) documenting lockfile, check-report, fix-plan, `require_claim`, and
  preset pack contracts.
- `Makefile` with 12 targets (`install`, `test`, `lint`, `fmt`, `fmt-check`,
  `typecheck`, `cover`, `build`, `smoke`, `clean`, `all`).
- GitHub issue templates (bug, feature), PR template, and `SECURITY.md`.
- Hero header with badges and terminal screenshot in `README.md`.

### Changed

- `SOURCE_PRECEDENCE` is now
  `["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]`.
  Consumers reading this array out of the lockfile should accept the new
  `preset` entry; the order is still load order, not priority.
- CI test matrix narrowed to Python 3.14 only. Supported runtime is still
  `>=3.11` per `pyproject.toml`.

### Fixed

- `doctor_repo_policy` no longer crashes on repos that extend a bundled
  preset. The staleness check now skips sources whose path starts with
  `preset:`, mirroring the fix already landed in
  `runtime/evaluator.py::_validate_lockfile_freshness`. Regression test in
  `tests/test_presets.py::test_doctor_repo_policy_with_extends_does_not_crash_on_preset_paths`.

## [0.1.0] - 2026-04-07

### Added

- Initial release: `cldc` CLI with commands `compile`, `doctor`, `check`,
  `ci`, `explain`, `fix`.
- Rule kinds: `deny_write`, `require_read`, `require_command`,
  `couple_change`.
- Modes: `observe`, `warn`, `block`, `fix`.
- Versioned JSON artifacts: policy lockfile, check report, fix plan, each
  with `$schema` and `format_version`.
- Git-aware CI entrypoints: staged and base/head diff evaluation.
- Deterministic source discovery and SHA-256 `source_digest`.

[Unreleased]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/AbdelStark/claude-md-compiler/releases/tag/v0.1.0
