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
Early implementation phase. The repo now ships a working `cldc` CLI with `compile`, `doctor`, `check`, and git-aware `ci` commands, canonical source discovery from nested paths, deterministic lockfile generation, schema-aware doctor diagnostics, runtime enforcement for `deny_write`, `require_read`, and `require_command` rules, CI-friendly JSON event ingestion for runtime checks, and one-command git diff evaluation for staged changes or base/head PR ranges.

## Install
```bash
python -m pip install -e .
cldc --version
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
cldc check . --write generated/output.json --json
cldc doctor . --json
```

`cldc doctor` validates more than file presence: it inspects the existing lockfile for malformed JSON, schema / format drift, rule-count mismatches, repo-root mismatches, stale artifacts, and full source-digest drift so operators can catch content changes even when timestamps and rule counts still look plausible. It also returns a single recommended next action so operators know what to do next.

`cldc check` loads the compiled lockfile and evaluates runtime evidence against the compiled policy. The current MVP covers `deny_write`, `require_read`, and `require_command`, emits stable JSON for automation, accepts both repo-relative and absolute in-repo paths, supports batch execution inputs from `--events-file` and `--stdin-json`, and refuses to enforce stale, schema-drifted, or source-drifted lockfiles so CI does not silently trust outdated policy artifacts.

`cldc ci` is the first git-aware wrapper around `cldc check`. It derives write paths from either `git diff --cached --name-only` (`--staged`) or `git diff --name-only <base>...<head>` (`--base` / `--head`), preserves the existing decision and violation JSON shape, and appends git provenance so CI can report exactly which diff source was evaluated.

## Shipping notes
- `cldc compile` must be rerun whenever policy sources change; the lockfile now carries a source digest and `doctor` / `check` will reject content drift even if timestamps are misleading.
- `cldc check` expects paths to stay inside the discovered repo root and will reject paths that escape it.
- `cldc check --events-file` and `cldc check --stdin-json` accept JSON shaped like `{"read_paths":[],"write_paths":[],"commands":[],"claims":[],"events":[...]}` where each event is a `read`, `write`, `command`, or `claim` object.
- `cldc ci` requires either `--staged` or `--base` (optionally with `--head`) so git provenance stays explicit instead of relying on hidden diff heuristics.
- `cldc doctor` is the fastest preflight when CI or local runs report lockfile drift.
