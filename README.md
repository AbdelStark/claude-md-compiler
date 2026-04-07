# claude-md-compiler

Compile CLAUDE.md into enforceable repo policy for Claude Code.

## North star
Turn CLAUDE.md from a passive instruction document into an active, versioned execution contract enforced across local runs, CI, and agent workflows.

## Why this repo exists
This is a private spec-first repo. It exists to turn a sharp product idea into a buildable system with enough precision that implementation can be delegated without hand-wavy gaps.

## What is in here
- `docs/specs/product-spec.md` — the full product specification
- `docs/rfcs/` — implementation contracts

## Current status
Early implementation phase. The repo now ships a working `cldc` CLI with `compile`, `doctor`, `check`, `explain`, `fix`, and git-aware `ci` commands, canonical source discovery from nested paths, deterministic lockfile generation, schema-aware doctor diagnostics, runtime enforcement for `deny_write`, `require_read`, and `require_command` rules, CI-friendly JSON event ingestion for runtime checks, one-command git diff evaluation for staged changes or base/head PR ranges, reviewer-friendly check summaries / recommended next actions, reusable explainability rendering from saved report artifacts or fresh evidence, first-pass report publishing via `--output` file export, and a remediation-planning slice that turns violations into deterministic follow-up steps and suggested commands.

## Install
```bash
uv tool install claude-md-compiler
cldc --version
```

Install directly from GitHub before the package is published:

```bash
uv tool install git+https://github.com/AbdelStark/claude-md-compiler
```

Set up a contributor checkout with the pinned Python and locked dev dependencies:

```bash
uv sync
uv run cldc --version
uv run pytest -q
```

If you only want the local checkout as a CLI tool, install it into your user tool environment:

```bash
uv tool install --editable .
```

`uv sync` creates `.venv`, installs the project in editable mode, and uses the committed `uv.lock` for repeatable contributor environments.

## Build and release validation
```bash
uv build --clear
uv run pytest -q
uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py
uv run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py
```

Manual publishing stays one command after a successful build:

```bash
uv publish --dry-run
uv publish
```

The repo also includes GitHub Actions workflows for CI and tag-driven PyPI publishing. Once PyPI trusted publishing is configured, shipping a release becomes:

```bash
git tag -a v0.1.0 -m v0.1.0
git push --tags
```

## Local usage
```bash
cldc doctor .
cldc compile .
cldc check . --write src/app.py --read docs/rfcs/CLDC-0006-validator-engine.md --command "pytest -q"
cldc check . --write /absolute/path/to/repo/src/app.py --json
cldc check . --events-file .cldc-events.json --json
printf '%s' '{"events":[{"kind":"write","path":"src/app.py"},{"kind":"command","command":"pytest -q"}]}' | cldc check . --stdin-json --json
cldc ci . --staged --json
cldc ci . --base origin/main --head HEAD --json
cldc explain . --write src/app.py
cldc explain . --events-file .cldc-events.json --format markdown
cldc explain . --report-file policy-report.json --format markdown
cldc fix . --write src/app.py --json
cldc fix . --report-file policy-report.json --format markdown
cldc check . --write generated/output.json --json
cldc check . --write generated/output.json --json --output artifacts/policy-report.json
cldc explain . --report-file artifacts/policy-report.json --format markdown --output artifacts/policy-explanation.md
cldc fix . --report-file artifacts/policy-report.json --json --output artifacts/policy-fix-plan.json
cldc doctor . --json
```

`cldc doctor` validates more than file presence: it inspects the existing lockfile for malformed JSON, schema / format drift, rule-count mismatches, repo-root mismatches, stale artifacts, and full source-digest drift so operators can catch content changes even when timestamps and rule counts still look plausible. It also returns a single recommended next action so operators know what to do next.

`cldc check` loads the compiled lockfile and evaluates runtime evidence against the compiled policy. The current MVP covers `deny_write`, `require_read`, and `require_command`, emits stable JSON for automation, accepts both repo-relative and absolute in-repo paths, supports batch execution inputs from `--events-file` and `--stdin-json`, surfaces a deterministic summary plus a single recommended next action, and refuses to enforce stale, schema-drifted, or source-drifted lockfiles so CI does not silently trust outdated policy artifacts.

`cldc ci` is the first git-aware wrapper around `cldc check`. It derives write paths from either `git diff --cached --name-only` (`--staged`) or `git diff --name-only <base>...<head>` (`--base` / `--head`), preserves the existing decision and violation JSON shape, appends git provenance, and now inherits the same explainable summary / next-action reporting as direct `cldc check` runs.

`cldc explain` turns either fresh runtime evidence or a previously saved JSON policy report into a reviewer-friendly explanation with rule provenance, rationale, and recommended next steps. Policy report JSON emitted by `cldc check`, `cldc ci`, and `cldc explain --json` now carries its own `$schema` and `format_version` so saved artifacts stay explicit and machine-validated across releases, while `cldc explain` still accepts legacy unversioned reports generated before this contract landed.

`cldc fix` is the first remediation-planning slice. It accepts either fresh runtime evidence or a saved policy report artifact, emits a versioned machine-readable fix-plan JSON contract, and renders deterministic text/Markdown guidance with linked files to inspect, suggested follow-up commands, and explicit next steps. The current slice is intentionally advisory only: it does not mutate the repo or run commands automatically.

## Saved-artifact workflow
```bash
# 1. Compile once after policy changes
cldc compile .

# 2. Evaluate a real change and publish the machine-readable report artifact
cldc check . --write generated/output.json --json --output artifacts/policy-report.json

# 3. Render a reviewer-facing explanation from the saved report artifact
cldc explain . --report-file artifacts/policy-report.json --format markdown --output artifacts/policy-explanation.md

# 4. Generate a saved remediation plan from that same report artifact
cldc fix . --report-file artifacts/policy-report.json --json --output artifacts/policy-fix-plan.json
```

`--output` writes the same content shown on stdout to disk and creates parent directories automatically, so CI or agent wrappers can publish stable artifacts without shell redirection tricks.

## Shipping notes
- `uv tool install claude-md-compiler` is the primary end-user install path once the package is published.
- `uv sync` is the primary contributor setup path; it installs the project plus the `dev` dependency group from `uv.lock`.
- `uv build --clear` produces both the wheel and source distribution in `dist/`.
- `tests/smoke_test.py` is designed to run against the built wheel or sdist so packaging regressions fail before publishing.
- `.github/workflows/publish.yml` expects a GitHub environment named `pypi` plus a matching PyPI trusted publisher configuration.
- `cldc compile` must be rerun whenever policy sources change; the lockfile now carries a source digest and `doctor` / `check` will reject content drift even if timestamps are misleading.
- `cldc check` expects paths to stay inside the discovered repo root and will reject paths that escape it.
- `cldc check --events-file` and `cldc check --stdin-json` accept JSON shaped like `{"read_paths":[],"write_paths":[],"commands":[],"claims":[],"events":[...]}` where each event is a `read`, `write`, `command`, or `claim` object.
- `cldc ci` requires either `--staged` or `--base` (optionally with `--head`) so git provenance stays explicit instead of relying on hidden diff heuristics.
- `cldc explain` can either render fresh evidence inputs or a saved JSON report artifact, but it intentionally refuses to mix those modes in one invocation.
- `cldc fix` follows the same input-mode split as `cldc explain`: use either fresh evidence flags or `--report-file` / `--stdin-report`, not both.
- `--output` is available on every CLI command and writes the exact emitted payload/rendered text to a file while still printing it to stdout.
- Saved policy report artifacts now include a top-level `$schema` plus `format_version`; `cldc explain` and `cldc fix` tolerate older unversioned artifacts for backwards compatibility, but new automation should keep the versioned fields intact.
- `cldc doctor` is the fastest preflight when CI or local runs report lockfile drift.
