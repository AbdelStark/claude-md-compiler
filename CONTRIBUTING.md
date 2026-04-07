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

The repository relies on both direct module tests and CLI regression tests.

- `tests/test_compiler.py`: lockfile generation and compile metadata
- `tests/test_runtime.py`: enforcement behavior and artifact validation
- `tests/test_cli.py`: end-to-end CLI contract
- `tests/test_validation.py`: malformed input and drift/error handling

Every bug fix should add a regression test.

## Documentation

Keep these files current when behavior changes:

- `README.md`
- `CLAUDE.md`
- `ARCHITECTURE.md`
- `CHANGELOG.md`

`docs/rfcs/` are treated as specification documents. Do not edit them casually as implementation notes.

## Release Checks

Before cutting a release, run:

```bash
uv run pytest -q
uv build
uv run cldc --version
```

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
