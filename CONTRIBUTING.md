# Contributing

## Prerequisites

- Python 3.11+
- `uv`
- `git`

## Setup

```bash
git clone https://github.com/AbdelStark/claude-md-compiler
cd claude-md-compiler
uv sync --locked
```

## Daily Commands

```bash
uv run pytest -q
uv build
uv run cldc --help
uv run cldc compile tests/fixtures/repo_a
uv run cldc check tests/fixtures/repo_a --write src/main.py --json
```

## Expected Workflow

1. Reproduce the behavior with a test when changing runtime logic.
2. Make the smallest coherent change that fixes the behavior.
3. Run the focused tests first, then `uv run pytest -q`.
4. Update public docs when the CLI surface, policy semantics, or artifact contracts change.

## Code Expectations

- Keep the core deterministic.
- Use explicit UTF-8 file I/O.
- Do not silently ignore malformed or unsupported compiled data.
- Prefer pure functions in ingest/parser/compiler/runtime layers.
- Keep `src/cldc/cli/main.py` thin; move logic into the library modules.

## Tests

The repository relies on direct module tests, CLI regression tests, property
tests, an opt-in end-to-end suite, and a post-build wheel smoke test. Add the
right kind of test for the layer you are changing:

| Test file | Layer under test |
| --- | --- |
| `tests/test_source_loader.py` | Ingest: discovery, source loading, inline blocks, `extends:` resolution. |
| `tests/test_rule_parser.py` | Parser: rule validation and normalization. |
| `tests/test_compiler.py` | Compiler: lockfile shape and digest stability. |
| `tests/test_runtime.py` | Runtime: evaluation of all rule kinds, evidence merging, git integration. |
| `tests/test_reporting.py` | Reporting: saved-report normalization and rendering. |
| `tests/test_presets.py` | Presets: loader API, bundled pack contents, `extends:` end-to-end. |
| `tests/test_hooks.py` | Hooks: `cldc hook generate`/`install` artifacts. |
| `tests/test_scaffold.py` | Scaffold: `cldc init` config + stub `CLAUDE.md`. |
| `tests/test_errors.py` | Typed exception hierarchy. |
| `tests/test_logging.py` | Library silence and CLI logging wiring. |
| `tests/test_tui.py` | TUI: state loaders + Pilot-driven smoke tests. |
| `tests/test_properties.py` | Hypothesis property tests. |
| `tests/test_benchmarks.py` | `pytest-benchmark` baselines (opt-in via `--benchmark-only`). |
| `tests/test_cli.py` | CLI contract: argparse wiring, exit codes, JSON output shape. |
| `tests/test_validation.py` | Cross-cutting: malformed input, schema drift, stale lockfile rejection. |
| `tests/e2e/` | End-to-end tests against `langchain-ai/langchain` (opt-in via `pytest -m e2e`). |
| `tests/smoke_test.py` | Post-build wheel smoke (`make smoke`). |

Every bug fix should add a regression test.

## Documentation

Keep these files current when behavior changes:

- `README.md`
- `CLAUDE.md`
- `ARCHITECTURE.md`
- `CHANGELOG.md`
- `docs/library-usage.md`

`docs/rfcs/` are treated as specification documents. Do not edit them casually as implementation notes.

## Release Checks

Before cutting a release, run:

```bash
uvx --from 'ruff>=0.6' ruff format --check src tests
uv run ruff check src tests
uv run pyright src
uv run pytest -q
uv build
make smoke
uv run cldc --version
```

## Publishing

When cutting a tagged release:

1. Update `pyproject.toml`, `CHANGELOG.md`, and any versioned examples or agent-context files that refer to the shipped surface.
2. Run the full release checks above.
3. Commit the release metadata bump and tag it as `vX.Y.Z`.
4. Push `main` and the new tag.
5. Publish the built artifacts with `uv publish`.

## Local quality gates

The `Makefile` provides a single command for the full local gate:

```bash
make all
```

Individual targets:

- `make install` — sync the locked dev env
- `make test` — run the pytest suite
- `make lint` / `make fmt` / `make fmt-check` — ruff lint and format
- `make typecheck` — pyright
- `make cover` — pytest with coverage
- `make build` / `make smoke` — wheel + sdist build and smoke test
- `make clean` — remove build/cache artifacts

Run `make help` for the full target list.
