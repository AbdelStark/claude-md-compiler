## Summary

One or two sentences describing the change.

## Type of change

- [ ] `fix`: bug fix
- [ ] `feat`: new feature or rule kind
- [ ] `docs`: documentation-only
- [ ] `chore`: tooling, CI, or release hygiene
- [ ] `test`: test-only
- [ ] `refactor`: behavior-preserving cleanup

## Checklist

- [ ] `uv run pytest -q` passes locally
- [ ] `make lint` (or `uvx ruff check src tests`) is clean
- [ ] `make typecheck` (or `uvx pyright src`) is clean
- [ ] `cldc doctor tests/fixtures/repo_a` succeeds
- [ ] Added or updated tests for the changed behavior
- [ ] Updated `README.md`, `CLAUDE.md`, `ARCHITECTURE.md`, or `CHANGELOG.md` if user-facing behavior changed
- [ ] Schema changes are gated by an RFC update in `docs/rfcs/` (if applicable)

## Reproduction / verification

How a reviewer can locally verify the change. Paste commands and expected output.

## Notes

Anything else reviewers should know.
