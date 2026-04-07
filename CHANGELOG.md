# Changelog

All notable changes to `claude-md-compiler` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
