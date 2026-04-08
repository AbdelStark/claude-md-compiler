# Changelog

All notable changes to `claude-md-compiler` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Narrated langchain e2e demo runner behind `make e2e`, with a visible
  pipeline map, colored stage cards, explicit ingest/parse/compile/runtime/
  doctor/fix-plan walkthrough, and optional timed or interactive pauses for
  recordings and live demos.

### Changed

- Raw pytest e2e coverage now lives behind `make e2e-test`; `make e2e`
  launches the visual demo flow instead of the plain pytest output.

## [0.2.0] - 2026-04-08

### Added

- Stateful Claude Code hook adapter that captures reads, writes, commands,
  command outcomes, and explicit claims across a session. The generated
  Claude settings now wire `SessionStart`, `PreToolUse`, `PostToolUse`,
  `PostToolUseFailure`, `Stop`, and `SessionEnd`, and `cldc hook claim`
  appends explicit claims into the saved session state.
- `require_command_success` rule kind: path-scoped workflow invariants can
  now require a listed command to complete successfully, rather than only
  checking that the command string appeared in the evidence set.
- Outcome-aware runtime evidence via `command_results`, plus
  `--command-success` and `--command-failure` on `check`, `explain`, and
  `fix` so embedders and CI wrappers can distinguish successful validation
  runs from failed ones.
- README and architecture/docs reframing around Anthropic's documented
  boundary that Claude treats `CLAUDE.md` as context, not enforced
  configuration. The docs now emphasize `cldc` as a workflow-invariant policy
  engine, versioned artifact generator, and deterministic judge between the
  agent and the repo.
- New `docs/library-usage.md` — full library reference covering every public
  symbol, the JSON shapes that `to_dict()` produces, the typed exception
  hierarchy, the determinism guarantees, and worked examples for each rule
  kind. Linked from the README, CONTRIBUTING, and CLAUDE.md.
- README rewrite for world-class open-source presentation: table of contents,
  60-second tour, full command-surface table, dedicated "Exit codes and JSON
  contracts" section with the `error_type` envelope, "Library API" section,
  expanded "Project status", and a "Learn more" hub with explicit links to
  ARCHITECTURE, library usage, RFCs, CONTRIBUTING, CHANGELOG, SECURITY.
- `tests/test_events.py` (19 tests) covering the file/text loaders for
  `load_execution_inputs_*`, every error branch in `load_execution_inputs`,
  and the `ExecutionInputs.merged_with` invariants. Lifts `events.py`
  coverage from 78% to 100%.
- `tests/test_remediation.py` (13 tests) covering `_normalize_fix_plan`'s
  validation paths: schema drift, format-version mismatch, malformed
  remediation lists, missing required fields, non-bool `can_autofix`,
  non-int counts, non-dict inputs, and nullable source-provenance fields.
- `tests/test_version.py` (5 tests) covering the
  `cldc.__version__`/`_read_source_version` resolver, including the
  `pyproject.toml`-missing fallback path and the repo-checkout preference over
  stale installed metadata.
- Module-level docstrings on every previously docstring-less module under
  `src/cldc/`: top-level package, CLI, ingest (discovery, source loader, init),
  parser (rule parser, init), compiler (policy compiler, init), runtime
  (evaluator, events, git, reporting, remediation, report_schema, init).
  Documents the role each module plays in the ingest → parser → compiler →
  runtime pipeline.
- `pyproject.toml` PyPI metadata polish: expanded `description`,
  contact-bearing `authors`/`maintainers`, broader `keywords` and
  `classifiers` (including `Typing :: Typed`, `Topic :: Utilities`, OS
  family classifiers), and `Documentation`/`Changelog`/`Source Code` URLs.
- `tests/smoke_test.py` now also asserts that `init` and `hook` show up in
  `cldc --help`, that bundled presets are listed, and that `cldc hook
  generate git-pre-commit` / `cldc hook generate claude-code` produce the
  expected content. The post-build wheel smoke now exercises the full
  shipped command surface.
- `Makefile`: existing `e2e`, `tui`, and `cover` targets are now reflected
  in the documented release / contributor flow.

### Changed

- `cldc.__version__` now prefers the checked-out repo version from
  `pyproject.toml` when available, then falls back to installed package
  metadata. This avoids stale `egg-info` state causing release/version drift
  in local development and CI.
- Removed the unused `_safe_resolve` helper from
  `src/cldc/compiler/policy_compiler.py`; the doctor report now resolves the
  repo path inline. No public API change.
- Test-suite hygiene: `tests/test_properties.py` import block sorted to
  isort/ruff layout; `tests/test_reporting.py` `pytest.raises(match=...)`
  patterns escaped with raw strings (RUF043).

### Fixed

- Claude hook report handoff now keeps the latest saved report in sync with
  command outcomes and explicit claims, and `cldc explain` / `cldc fix` can
  load the latest Claude hook report directly by session id.
- `ARCHITECTURE.md` now lists every test file and points at every CLI
  subparser the package actually ships (`init`, `hook`, `tui`, plus the
  long-standing seven). `CONTRIBUTING.md` test layout matches.
- `CLAUDE.md` repository map now lists `_logging`, `errors`, and the
  `runtime/report_schema.py` indirection module that exists to break what
  would otherwise be a circular import between the evaluator and the
  reporting layer.

### Added (previous polish phase carry-over)

- New `cldc hook` command — generates and installs hook scripts that
  bridge the gap between policy enforcement and the actual moments work
  is finished. `cldc hook generate git-pre-commit` prints a portable
  POSIX `pre-commit` script that runs `cldc ci --staged` against the
  compiled lockfile and aborts the commit on blocking violations.
  `cldc hook generate claude-code` prints a `.claude/settings.json`
  snippet that wires `cldc check` into the Claude Code agent harness as
  a `PostToolUse` hook on `Edit|Write|MultiEdit`. `cldc hook install
  git-pre-commit` writes the script directly into `.git/hooks/pre-commit`,
  marks it executable, and refuses to clobber an existing hook unless
  `--force` is passed. Backed by a new `cldc.runtime.hooks` module with
  `HookArtifact`, `HookInstallReport`, `generate_hook`, and `install_hook`
  entry points; covered by 17 unit and CLI tests in `tests/test_hooks.py`.
- New `cldc init` command — scaffolds a repo's `.claude-compiler.yaml`
  from one or more bundled presets (`--preset default --preset strict`,
  repeatable) and writes a stub `CLAUDE.md` if none exists. Never
  overwrites an existing `CLAUDE.md`; refuses to clobber an existing
  `.claude-compiler.yaml` unless `--force` is passed. `--json` emits a
  machine-readable init report with `created`/`updated`/`skipped`
  lists and a `next_action` hint pointing at `cldc compile`. Backed by
  a new `cldc.scaffold` module with `initialize_repo_policy` and
  `InitReport`.
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

[Unreleased]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/AbdelStark/claude-md-compiler/releases/tag/v0.1.0
