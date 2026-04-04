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
Early implementation phase. The repo now ships a working `cldc` CLI with `compile` and `doctor` commands, canonical source discovery from nested paths, deterministic lockfile generation, and validation tests for source loading and rule parsing.
