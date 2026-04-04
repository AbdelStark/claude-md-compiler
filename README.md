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
Early implementation phase. The repo now ships a working `cldc` CLI with `compile`, `doctor`, and MVP `check` commands, canonical source discovery from nested paths, deterministic lockfile generation, schema-aware doctor diagnostics, and runtime enforcement for `deny_write`, `require_read`, and `require_command` rules.

## Local usage
```bash
python -m pip install -e .
cldc doctor .
cldc compile .
cldc check . --write src/app.py --read docs/rfcs/CLDC-0006-validator-engine.md --command "pytest -q"
cldc check . --write generated/output.json --json
cldc doctor . --json
```

`cldc doctor` now validates more than file presence: it inspects the existing lockfile for malformed JSON, schema / format drift, rule-count mismatches, and stale artifacts, then returns a single recommended next action so operators know what to do next.

`cldc check` loads the compiled lockfile and evaluates runtime evidence against the compiled policy. The first MVP covers `deny_write`, `require_read`, and `require_command`, emits stable JSON for automation, and returns exit code `2` when any blocking rule is violated.
