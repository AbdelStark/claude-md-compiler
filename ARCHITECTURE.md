# Architecture

`cldc` compiles repository policy from `CLAUDE.md`, `.claude-compiler.yaml`,
`policies/*.yml`, and bundled preset packs into a versioned lockfile, then
enforces that lockfile against runtime evidence (reads, writes, commands,
claims) and git-derived diffs with explainable, deterministic decisions. The
codebase is structured as a pure-core / thin-shell pipeline so each layer can
be tested in isolation and re-used by other tools.

## Layered design

| Layer | Location | Responsibility |
| --- | --- | --- |
| Ingest | `src/cldc/ingest/` | Find the repo root and load canonical policy sources. |
| Parser | `src/cldc/parser/` | Validate and normalize rule documents. |
| Compiler | `src/cldc/compiler/` | Produce the versioned lockfile artifact. |
| Runtime | `src/cldc/runtime/` | Evaluate evidence, render reports, build fix plans, integrate with git. |
| CLI | `src/cldc/cli/` | Thin argparse shell that delegates to the layers above. |
| TUI | `src/cldc/tui/` | Textual-based interactive explorer that delegates to the same library calls. |

A separate `src/cldc/presets/` subpackage ships bundled opinionated policy
packs (`default`, `strict`, `docs-sync`) and the loader API used by the ingest
layer when a `.claude-compiler.yaml` extends a preset.

Primary modules per layer:

- Ingest: `src/cldc/ingest/discovery.py` (`discover_policy_repo`,
  `DiscoveryResult`) and `src/cldc/ingest/source_loader.py`
  (`load_policy_sources`, `SourceBundle`, `SOURCE_PRECEDENCE`).
- Parser: `src/cldc/parser/rule_parser.py` (`parse_rule_documents`,
  `ParsedPolicy`, `RuleDefinition`, `ALLOWED_RULE_KINDS`,
  `REQUIRED_FIELDS_BY_KIND`).
- Compiler: `src/cldc/compiler/policy_compiler.py` (`compile_repo_policy`,
  `doctor_repo_policy`, `LOCKFILE_SCHEMA`, `LOCKFILE_FORMAT_VERSION`).
- Runtime: `src/cldc/runtime/evaluator.py` (`check_repo_policy`,
  `CheckReport`, `Violation`), `src/cldc/runtime/events.py`
  (`ExecutionInputs`, `load_execution_inputs`),
  `src/cldc/runtime/reporting.py` (`load_check_report`,
  `render_check_report`), `src/cldc/runtime/remediation.py` (`build_fix_plan`,
  `render_fix_plan`, `FIX_PLAN_SCHEMA`), `src/cldc/runtime/git.py`
  (`collect_git_write_paths`), `src/cldc/runtime/report_schema.py`
  (`CHECK_REPORT_SCHEMA`, `CHECK_REPORT_FORMAT_VERSION`).
- Presets: `src/cldc/presets/loader.py` (`list_presets`, `load_preset`,
  `preset_path`, `PresetNotFoundError`, `PRESET_SOURCE_KIND`).
- CLI: `src/cldc/cli/main.py` (argparse subparsers for `compile`, `doctor`,
  `check`, `ci`, `explain`, `fix`, `preset`, `tui`).
- TUI: `src/cldc/tui/app.py` (`CldcApp`, `run_tui`, modal screens for presets
  and doctor), `src/cldc/tui/state.py` (`TuiState`, `Evidence`,
  `discover_state`, `recompile_state`, `run_check`),
  `src/cldc/tui/widgets.py` (`RepoBar`, `SourcesPane`, `RulesPane`,
  `DetailPane`, `EvidenceForm`, `DecisionPanel`), and
  `src/cldc/tui/styles.tcss` (dark theme with focus-aware borders and mode
  badges). The TUI never talks to the filesystem directly — every mutation
  flows through the ingest / parser / compiler / runtime layers, so what you
  see on screen is what `cldc` would produce in a headless run.

## Data flow

```
                    +---------------------------+
  source files ---> | discover_policy_repo      |  (ingest/discovery.py)
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    | load_policy_sources       |  (ingest/source_loader.py)
                    | -> SourceBundle           |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    | parse_rule_documents      |  (parser/rule_parser.py)
                    | -> ParsedPolicy           |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    | compile_repo_policy       |  (compiler/policy_compiler.py)
                    | -> .claude/policy.lock.json
                    +-------------+-------------+
                                  |
       runtime evidence           v
       (--read/--write/...)       |
       --events-file       +---------------------------+
       --stdin-json -----> | check_repo_policy         |  (runtime/evaluator.py)
       --claim             | -> CheckReport            |
                           +------+----------------+----+
                                  |                |
                                  v                v
                  +---------------------+  +------------------------+
                  | render_check_report |  | build_fix_plan         |
                  | (text / markdown)   |  | -> fix plan JSON       |
                  | runtime/reporting.py|  | runtime/remediation.py |
                  +---------------------+  +------------------------+
```

For CI flows, `collect_git_write_paths` in `src/cldc/runtime/git.py` sources
the write set from staged changes or a `--base`/`--head` diff before evidence
is handed to `check_repo_policy`.

## Schema contracts

Three JSON artifacts are versioned contracts. Each carries a `$schema` URI and
a string `format_version` so consumers can detect drift early.

| Artifact | `$schema` | `format_version` | Emitter | Consumer |
| --- | --- | --- | --- | --- |
| Policy lockfile | `https://cldc.dev/schemas/policy-lock/v1` | `1` | `cldc compile` writes `.claude/policy.lock.json` | `cldc check`, `ci`, `explain`, `fix`, `doctor` |
| Check report | `https://cldc.dev/schemas/policy-report/v1` | `1` | `cldc check --json`, `cldc ci --json` | `cldc explain --report-file`, `cldc fix --report-file` |
| Fix plan | `https://cldc.dev/schemas/policy-fix-plan/v1` | `1` | `cldc fix --json` | Downstream tools and CI dashboards |

Any change to the shape of these artifacts is a breaking change and requires a
major version bump on both the schema URI (`/v2`) and the `format_version`
string. RFC-style specifications for these contracts live under `docs/rfcs/`
and are added incrementally as the contract surface stabilizes.

## Rule model

| Kind | Required fields | Meaning |
| --- | --- | --- |
| `deny_write` | `paths` | Paths matching `paths` must not be written. |
| `require_read` | `paths`, `before_paths` | Writing `paths` requires a prior read matching `before_paths`. |
| `require_command` | `commands`, `when_paths` | Writing `when_paths` requires at least one listed command to run. |
| `couple_change` | `paths`, `when_paths` | Writing `paths` requires a companion write matching `when_paths`. |
| `require_claim` | `claims`, `when_paths` | Writing `when_paths` requires at least one listed claim to be asserted. |

The canonical set lives in `ALLOWED_RULE_KINDS` and `REQUIRED_FIELDS_BY_KIND`
in `src/cldc/parser/rule_parser.py`. Each rule may declare a `mode` of
`observe`, `warn`, `block`, or `fix`; `block` and `fix` are the blocking modes
that cause `cldc check` to exit with code `2`.

## Source precedence

`SOURCE_PRECEDENCE` in `src/cldc/ingest/source_loader.py` is the canonical
ordered list of source kinds:

```python
SOURCE_PRECEDENCE = ["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]
```

Order matters for two reasons:

1. The compiler walks sources in this order to build the `SourceBundle`, so
   the SHA-256 `source_digest` is byte-stable across runs as long as the input
   files are unchanged.
2. Later sources do not silently shadow earlier ones. The parser detects
   duplicate rule ids across sources and raises a validation error rather than
   letting one source quietly override another. Ordering exists to make
   merges deterministic, not to express priority.

The `preset` slot is reserved for bundled packs pulled in via `extends:` in
`.claude-compiler.yaml`. Its source kind constant lives in
`src/cldc/presets/loader.py` as `PRESET_SOURCE_KIND`.

## Invariants

These properties hold across the codebase. Tests in `tests/test_validation.py`
defend the most critical ones.

- Determinism: lockfile output is byte-stable for the same inputs. JSON keys
  are sorted, lists preserve insertion order, and digests are SHA-256 over a
  canonicalized source bundle.
- Repo-local paths: runtime path normalization in
  `src/cldc/runtime/evaluator.py` rejects any path that escapes the discovered
  repo root. Include patterns in `src/cldc/ingest/source_loader.py` are also
  validated to stay inside the repo.
- Fail-closed: malformed lockfiles, schema drift, stale `source_digest`
  values, and unknown rule kinds raise explicit errors. Nothing degrades to a
  silent pass.
- Versioned artifacts: every JSON artifact carries `$schema` plus
  `format_version`. Consumers refuse mismatched versions instead of guessing.
- Explicit UTF-8: every file read or write that touches repo content passes
  `encoding="utf-8"` rather than relying on the platform default.

## Extension points

Adding a new rule kind:

1. Add the kind to `ALLOWED_RULE_KINDS` and its required fields to
   `REQUIRED_FIELDS_BY_KIND` in `src/cldc/parser/rule_parser.py`.
2. Add an evaluation branch in `_evaluate_rule` in
   `src/cldc/runtime/evaluator.py` and corresponding violation explanation in
   `_explain_violation`.
3. Extend `_steps_for_violation` in `src/cldc/runtime/remediation.py` so the
   fix plan can describe a remediation.
4. Add tests in `tests/test_rule_parser.py`, `tests/test_runtime.py`, and
   `tests/test_validation.py`.

Adding a new preset pack:

1. Drop a YAML document into `src/cldc/presets/packs/` with the same shape as
   `default.yml`.
2. The loader auto-discovers any `*.yml` file under that directory; no code
   change is needed.
3. Add coverage in `tests/test_presets.py`.

Adding a new runtime evidence source:

1. Extend `ExecutionInputs` in `src/cldc/runtime/events.py` with the new
   field, and update `merged_with`, `EMPTY_EXECUTION_INPUTS`, and
   `_parse_event` plus `ALLOWED_EVENT_KINDS`.
2. Update `_add_runtime_input_flags` in `src/cldc/cli/main.py` so the CLI
   surfaces the new flag.
3. Add a new matcher helper in `src/cldc/runtime/evaluator.py` and consume it
   from `_evaluate_rule`.
4. Add tests in `tests/test_runtime.py` and `tests/test_cli.py`.

## Testing layers

Each layer has a dedicated test module so failures point at one place.

| Test file | Layer under test |
| --- | --- |
| `tests/test_source_loader.py` | Ingest: discovery, source loading, inline blocks, `extends:` resolution. |
| `tests/test_rule_parser.py` | Parser: rule validation and normalization. |
| `tests/test_compiler.py` | Compiler: lockfile shape, digest stability, `doctor` diagnostics. |
| `tests/test_runtime.py` | Runtime: evaluation of all rule kinds, evidence merging, git integration. |
| `tests/test_presets.py` | Presets: loader API, bundled pack contents, `extends:` end-to-end. |
| `tests/test_cli.py` | CLI contract: argparse wiring, exit codes, JSON output shape. |
| `tests/test_validation.py` | Cross-cutting: malformed input, schema drift, stale lockfile rejection. |
| `tests/smoke_test.py` | Post-build wheel smoke; run against `dist/*.whl` after `uv build`. |

The canonical fixture repository lives at `tests/fixtures/repo_a/` and is
shared between compile, runtime, and CLI tests so the same policy is exercised
end to end.
