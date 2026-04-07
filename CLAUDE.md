# claude-md-compiler Agent Context

## Project Identity

`cldc` compiles repository policy from `CLAUDE.md` and related YAML files into `.claude/policy.lock.json`, then enforces that policy over explicit runtime evidence and git-derived diffs.

## Tech Stack

- Language: Python 3.11+
- Packaging: `uv` with `uv_build`
- Runtime dependency: `PyYAML`
- Test runner: `pytest`
- Entry point: `cldc`

## Repository Map

- `src/cldc/cli/main.py`: argparse CLI, command routing, exit codes, JSON/text output.
- `src/cldc/ingest/discovery.py`: repo-root discovery and source inventory.
- `src/cldc/ingest/source_loader.py`: source loading, inline `cldc` block extraction, include-pattern validation.
- `src/cldc/parser/rule_parser.py`: rule validation and normalized policy model.
- `src/cldc/compiler/policy_compiler.py`: lockfile generation and `doctor` diagnostics.
- `src/cldc/runtime/evaluator.py`: policy evaluation against reads, writes, commands, and git-derived write sets.
- `src/cldc/runtime/events.py`: machine-readable runtime evidence ingestion.
- `src/cldc/runtime/reporting.py`: saved report validation and rendering.
- `src/cldc/runtime/remediation.py`: deterministic fix-plan generation and rendering.
- `src/cldc/runtime/git.py`: staged and base/head diff collection.
- `tests/fixtures/repo_a/`: canonical fixture repo used by compile/runtime/CLI tests.
- `docs/rfcs/`: frozen implementation contracts.

## Build, Test, and Run

```bash
uv sync --locked
uv run pytest -q
uv build
uv run cldc --help
uv run cldc compile tests/fixtures/repo_a
uv run cldc check tests/fixtures/repo_a --write src/main.py --json
uv run cldc ci tests/fixtures/repo_a --base HEAD --head HEAD --json
uv run cldc explain tests/fixtures/repo_a --write src/main.py --format markdown
uv run cldc fix tests/fixtures/repo_a --write src/main.py --json
```

## Conventions

- Use explicit `encoding="utf-8"` for repository file I/O.
- Keep JSON artifacts deterministic: sorted keys, stable ordering, explicit schema/version fields.
- Fail closed on malformed or tampered artifacts; do not silently ignore unsupported rule kinds.
- Keep the CLI shell thin. Put behavior in ingest/parser/compiler/runtime modules, then expose it in `cli/main.py`.
- Add or update tests with every behavior change, especially for stale lockfiles, malformed inputs, and boundary cases.

## Critical Constraints

- Do not change `docs/rfcs/` unless the specification itself is changing.
- Treat `.claude/policy.lock.json`, policy report JSON, and fix-plan JSON as versioned contracts.
- `cldc check` must refuse stale or schema-drifted lockfiles instead of guessing.
- Rule kinds that are not supported by the runtime must raise explicit errors, not degrade to a silent pass.
- Keep include patterns repo-local; do not allow config globs to escape the repo root.

## Gotchas

- This repository has a top-level `CLAUDE.md` for agent context, but it intentionally contains no `cldc` rules.
- `require_claim` is a path-scoped rule: writes matching `when_paths` fail the rule unless at least one of the listed `claims` is asserted via `--claim`, an events file, stdin JSON, or an event payload.
- `couple_change` means a write matching `paths` requires an additional write matching `when_paths`; the same path does not satisfy both sides of the rule.
- `compile` updates the lockfile state in its returned metadata; missing-lockfile warnings from discovery should not survive a successful compile.

## Current State

As of April 7, 2026, the shipped CLI surface is `compile`, `doctor`, `check`, `ci`, `explain`, and `fix`.

Implemented:

- deterministic source discovery and lockfile generation
- doctor diagnostics for malformed, stale, and drifted artifacts
- runtime enforcement for `deny_write`, `require_read`, `require_command`, `couple_change`, and `require_claim`
- claim ingestion via `--claim`, events file, stdin JSON, and event payloads
- saved policy report rendering and deterministic fix-plan generation
- git-aware CI entrypoints for staged and base/head diffs

Known limitations:

- no preset policy packs
- no automatic repo mutation or autofix execution
- no separate lint/type/coverage enforcement in CI yet
