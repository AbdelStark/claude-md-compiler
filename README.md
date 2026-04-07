<div align="center">

# claude-md-compiler

**Compile `CLAUDE.md` into a versioned policy lockfile and enforce it against file edits, commands, and git diffs.**

[![PyPI](https://img.shields.io/pypi/v/claude-md-compiler.svg?logo=pypi&logoColor=white)](https://pypi.org/project/claude-md-compiler/)
[![Python](https://img.shields.io/pypi/pyversions/claude-md-compiler.svg?logo=python&logoColor=white)](https://pypi.org/project/claude-md-compiler/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-de5fe9?logo=python&logoColor=white)](https://github.com/astral-sh/uv)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/AbdelStark/claude-md-compiler)

![cldc terminal preview](./docs/assets/img/screenshot-1.png)

</div>

## What It Does

`cldc` is a Python CLI that compiles repository policy from `CLAUDE.md`, `.claude-compiler.yaml`, and `policies/*.yml` into a versioned lockfile, then checks file edits, commands, and git diffs against that policy.

## Why It Exists

`CLAUDE.md` is usually advisory text. `cldc` turns repo rules into a deterministic artifact that local runs, CI, and review tooling can enforce the same way every time.

## Who It Is For

- Developers using agentic coding tools in real repositories.
- Platform or infra teams that want repo-level guardrails.
- Maintainers who want explainable, local-first policy checks instead of hidden heuristics.

## Install

`cldc` requires Python 3.11+.

```bash
# persistent install
uv tool install claude-md-compiler

# or
pipx install claude-md-compiler

# one-shot
uvx --from claude-md-compiler cldc --version
```

For local development inside this repository, use the [development workflow](#development) instead of installing the project into itself.

## Quickstart

```bash
# 1. Compile policy into .claude/policy.lock.json
cldc compile .

# 2. Check a change directly
cldc check . --write src/main.py --command "pytest -q"

# 3. Explain or save the report
cldc explain . --write src/main.py --format markdown

# 4. Generate a remediation plan
cldc fix . --write src/main.py --format markdown

# 5. Gate a staged diff or PR range
cldc ci . --staged
cldc ci . --base origin/main --head HEAD

# 6. Or explore everything interactively in the terminal
cldc tui .
```

## Interactive TUI

`cldc tui` launches a Textual-powered terminal UI for exploring a repo's policy
without leaving the shell. It shows the discovered sources, the rule table with
live mode badges, the selected rule's full definition, a four-field evidence
form (reads / writes / commands / claims), and a colored decision panel that
updates on every check.

Keybindings:

| Key     | Action |
| ------- | --- |
| `c`     | Compile the repo (`cldc compile`) |
| `r`     | Run a check against the current evidence |
| `d`     | Open the doctor report |
| `p`     | Browse bundled preset packs |
| `R`     | Reload sources from disk |
| `ctrl+l` | Clear the evidence form |
| `?`     | Show help |
| `q`     | Quit |

The TUI uses only the same library calls as the non-interactive CLI, so the
behavior you see on screen is the behavior a `cldc check` in CI would produce.

## End-to-end test against a real repo

The repo ships an opt-in e2e test suite that demonstrates the full
compile → check → fix flow against a real upstream repo. By default it
clones [langchain-ai/langchain](https://github.com/langchain-ai/langchain),
drops a hand-authored `.claude-compiler.yaml` (under
`tests/e2e/compiler.yaml`) that translates langchain's CLAUDE.md prose
into enforceable rules, and walks through:

- a **red phase**: edits that should violate specific rules and the
  decision is `block` with a non-zero exit code,
- a **green phase**: a complete evidence set that satisfies every rule
  and the decision is `pass`,
- a **fix-plan phase**: building a remediation plan from the red report
  and asserting the steps reference the right rules.

Run it with:

```bash
make e2e
# or
uv run pytest -m e2e -v
```

The suite is excluded from the default `pytest` run via the `e2e`
marker, so it never slows down regular CI. It requires `git` on `PATH`
and network access; both are checked at collection time and produce a
clean `pytest.skip` if missing.

Exit codes:

- `0`: clean or non-blocking result (decisions `pass` or `warn`)
- `1`: runtime or input error (malformed repo, bad evidence payload, git failure, etc.)
- `2`: blocking policy violations (decisions `block`)

Every command supports `--json`, and every command can also persist its output with `--output <file>`. When a command fails (exit 1), the `--json` error payload carries `error_type` (the exception class, e.g. `LockfileError`, `GitError`, `FileNotFoundError`) so machine consumers can route on the failure mode without regex-parsing the message.

Global flags on the top-level `cldc` command:

- `--verbose`, `-v`: emit debug-level diagnostics to stderr and print the full traceback on errors. Use this when filing bugs.
- `--quiet`, `-q`: suppress warnings, leaving only errors.
- `--version`: print the package version.

## How Policy Is Authored

Sources are discovered from the repo root or any nested path inside the repo. Merge order is deterministic:

1. `CLAUDE.md`
2. inline fenced ```` ```cldc ```` blocks inside `CLAUDE.md`
3. `.claude-compiler.yaml` or `.claude-compiler.yml`
4. bundled presets referenced from `.claude-compiler.yaml` via `extends:`
5. `policies/*.yml` and `policies/*.yaml`

Example:

````markdown
# CLAUDE.md

```cldc
rules:
  - id: generated-lock
    kind: deny_write
    mode: block
    paths: ["generated/**"]
    message: Generated files must not be edited by hand.
```
````

```yaml
# .claude-compiler.yaml
default_mode: warn
extends:
  - default        # bundled preset: generated/** is read-only, lockfile-follows-manifest
  - strict         # bundled preset: tests-follow-source, arch-read, ci-green claim
rules:
  - id: keep-tests-in-sync
    kind: couple_change
    paths: ["src/**"]
    when_paths: ["tests/**"]
    message: Update tests when source changes.
```

## Preset Policy Packs

`cldc` ships with opinionated rule packs you can merge into your repo policy via `extends:` in `.claude-compiler.yaml`.

| Preset | What it does |
| --- | --- |
| `default` | Blocks writes to `generated/**`, `dist/**`, `build/**`; warns when a dependency manifest changes without a matching `install`/`sync`/`tidy` command. |
| `strict` | Requires tests to move with source, requires an architecture/RFC read before editing `src/**`, and requires a `ci-green` claim to ship `src/**` changes. |
| `docs-sync` | Couples public CLI / runtime / API changes with README/docs updates, and couples version bumps with changelog entries. |

Inspect the bundled packs:

```bash
cldc preset list
cldc preset show default
cldc preset show strict --json
```

Use them by listing one or more names under `extends:`:

```yaml
# .claude-compiler.yaml
extends:
  - default
  - docs-sync
```

Preset rules merge alongside your own rules. Duplicate rule IDs fail the compile, so pick unique IDs for your own rules.

## Rule Model

| Kind | Meaning |
| --- | --- |
| `deny_write` | Paths matching `paths` must not be written. |
| `require_read` | Writing `paths` requires a prior read matching `before_paths`. |
| `require_command` | Writing `when_paths` requires at least one listed command to run. |
| `couple_change` | Writing `paths` requires a companion write matching `when_paths`. |
| `require_claim` | Writing `when_paths` requires at least one listed policy `claims` to be asserted. |

Example `require_claim` rule — block edits to `src/**` until a reviewer asserts `qa-reviewed`:

```yaml
rules:
  - id: qa-sign-off
    kind: require_claim
    mode: block
    when_paths: ["src/**"]
    claims: ["qa-reviewed", "security-reviewed"]
    message: QA or security must sign off before editing source.
```

| Mode | Meaning |
| --- | --- |
| `observe` | Record the result but do not block. |
| `warn` | Report the result but do not block. |
| `block` | Report the result and exit `2`. |
| `fix` | Report the result as blocking and include remediation guidance. |

## Evidence Inputs

Runtime commands accept evidence three ways:

```bash
# direct flags
cldc check . --read docs/spec.md --write src/main.py --command "pytest -q" --claim qa-reviewed

# JSON file
cldc check . --events-file .cldc-events.json --json

# stdin JSON
cat .cldc-events.json | cldc check . --stdin-json --json
```

Use `--claim` once per asserted claim; claims satisfy `require_claim` rules in the compiled policy.

Accepted payload shape:

```json
{
  "read_paths": ["docs/spec.md"],
  "write_paths": ["src/main.py"],
  "commands": ["pytest -q"],
  "claims": ["qa-reviewed"],
  "events": [
    {"kind": "read", "path": "docs/spec.md"},
    {"kind": "write", "path": "src/main.py"},
    {"kind": "command", "command": "pytest -q"},
    {"kind": "claim", "claim": "qa-reviewed"}
  ]
}
```

Saved report workflow:

```bash
cldc check . --write src/main.py --json --output artifacts/policy-report.json
cldc explain . --report-file artifacts/policy-report.json --format markdown --output artifacts/policy-report.md
cldc fix . --report-file artifacts/policy-report.json --json --output artifacts/policy-fix-plan.json
```

## Architecture

`cldc` has a pure-core / thin-shell shape:

- `src/cldc/ingest/`: discover the repo root and load canonical policy sources.
- `src/cldc/parser/`: validate and normalize rule documents.
- `src/cldc/compiler/`: build `.claude/policy.lock.json` and doctor the repo state.
- `src/cldc/runtime/`: evaluate evidence, render reports, build fix plans, and integrate with git.
- `src/cldc/cli/`: expose the commands and exit-code behavior.

## Development

```bash
git clone https://github.com/AbdelStark/claude-md-compiler
cd claude-md-compiler
uv sync --locked
uv run pytest -q
uv build
```

Useful local commands:

```bash
uv run cldc --help
uv run cldc compile tests/fixtures/repo_a
uv run cldc check tests/fixtures/repo_a --write src/main.py --json
uv run cldc ci tests/fixtures/repo_a --base HEAD --head HEAD --json
uv run cldc explain tests/fixtures/repo_a --write src/main.py --format markdown
uv run cldc fix tests/fixtures/repo_a --write src/main.py --json
```

The repository does not require runtime environment variables.

## Learn More

- [ARCHITECTURE.md](./ARCHITECTURE.md) — layered design, data flow, schema contracts, and extension points
- [CHANGELOG.md](./CHANGELOG.md) — release history in Keep a Changelog format

## License

MIT. See [LICENSE](./LICENSE).
