---
name: Bug report
about: Report an unexpected cldc behavior so we can fix it
title: "bug: "
labels: ["bug"]
---

## Summary

One-sentence description of what went wrong.

## Reproduction

```bash
# Minimal commands that reproduce the bug
cldc --version
cldc compile path/to/repo
cldc check path/to/repo --write src/foo.py
```

## Expected behavior

What should have happened instead.

## Actual behavior

What actually happened, including the exit code and any JSON payloads.

## Environment

- `cldc --version`:
- Python version (`python --version`):
- OS:
- Installation method: `uv tool install` / `pipx` / `uvx` / editable

## Policy sources

Paste or summarize the relevant `CLAUDE.md`, `.claude-compiler.yaml`, `policies/*.yml`, or `extends:` entries.

## Lockfile metadata (if applicable)

```json
{
  "$schema": "...",
  "format_version": "...",
  "source_digest": "..."
}
```

## Additional context

Anything else that might help.
