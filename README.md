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
Early implementation phase. The repo now ships a working `cldc` CLI with `compile`, `doctor`, and MVP `check` commands, canonical source discovery from nested paths, deterministic lockfile generation, schema-aware doctor diagnostics, runtime enforcement for `deny_write`, `require_read`, and `require_command` rules, and CI-friendly JSON event ingestion for runtime checks.

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
cldc check . --write generated/output.json --json
cldc doctor . --json
```

`cldc doctor` validates more than file presence: it inspects the existing lockfile for malformed JSON, schema / format drift, rule-count mismatches, repo-root mismatches, and stale artifacts, then returns a single recommended next action so operators know what to do next.

`cldc check` loads the compiled lockfile and evaluates runtime evidence against the compiled policy. The current MVP covers `deny_write`, `require_read`, and `require_command`, emits stable JSON for automation, accepts both repo-relative and absolute in-repo paths, supports batch execution inputs from `--events-file` and `--stdin-json`, and refuses to enforce stale or schema-drifted lockfiles so CI does not silently trust outdated policy artifacts.

## Shipping notes
- `cldc compile` must be rerun whenever policy sources change.
- `cldc check` expects paths to stay inside the discovered repo root and will reject paths that escape it.
- `cldc check --events-file` and `cldc check --stdin-json` accept JSON shaped like `{"read_paths":[],"write_paths":[],"commands":[],"claims":[],"events":[...]}` where each event is a `read`, `write`, `command`, or `claim` object.
- `cldc doctor` is the fastest preflight when CI or local runs report lockfile drift.
