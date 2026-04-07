# Changelog

All notable user-visible changes to this project will be documented here.

## Unreleased

### Fixed

- Enforced `couple_change` rules during runtime checks instead of silently ignoring them.
- Runtime evaluation now fails closed on unsupported compiled rule kinds instead of degrading to a false `pass`.
- `compile` output now reflects the lockfile it just wrote rather than reporting the lockfile as missing.

### Changed

- Compiler config include patterns are now validated to stay inside the repo root.
- Core file I/O for policy artifacts and saved reports now uses explicit UTF-8 encoding.

### Documentation

- Rewrote the README to match the shipped CLI and current alpha status.
- Added architecture and contributing guides.
- Refreshed `CLAUDE.md` so agent context matches the current codebase.

## 0.1.0

- Initial alpha release of the `compile`, `doctor`, `check`, `ci`, `explain`, and `fix` workflow.
- Versioned lockfile, policy report, and fix-plan artifact contracts.
