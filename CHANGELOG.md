# Changelog

All notable changes to `claude-md-compiler` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - Unreleased

### Added

- `require_claim` rule kind: writes matching `when_paths` are blocked unless
  one of the listed `claims` is asserted via `--claim`, `--events-file`,
  `--stdin-json`, or an event payload of kind `claim`. Claims were previously
  ingested but never enforced, so this closes a real bypass.
- `--claim` CLI flag on `check`, `ci`, `explain`, and `fix`. The flag is
  repeatable; each invocation adds one asserted claim to the runtime evidence
  set before evaluation.
- Bundled preset policy packs under `src/cldc/presets/packs/`:
  - `default` blocks generated writes and warns on manifests touched without
    a paired lockfile sync.
  - `strict` enforces tests-follow-source coupling, architecture reads, and a
    `ci-green` claim before merging.
  - `docs-sync` couples public surface changes with README and docs updates.
- `cldc preset list` and `cldc preset show NAME` subcommands for inspecting
  bundled packs without leaving the CLI.
- `extends:` directive in `.claude-compiler.yaml` that merges named bundled
  presets into the compiled lockfile alongside repo-local rules. Conflicts
  are surfaced as parser errors rather than silently overridden.
- `matched_claims` and `required_claims` fields on violations and
  `suggested_claims` on fix-plan remediations, so explainable output and
  remediation can both reason about claim state.
- New `preset` source kind in `SOURCE_PRECEDENCE`, exported as
  `PRESET_SOURCE_KIND` from `cldc.presets`.
- Hero header with badges and terminal screenshot in `README.md`.

### Changed

- `SOURCE_PRECEDENCE` is now
  `["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]`.
  Consumers reading this array out of the lockfile should accept the new
  `preset` entry; the order is still load order, not priority.

### Fixed

- Placeholder. Unit 1 lands a fix for the latent `doctor` crash on
  preset-using repos in a parallel branch; if that change merges first, move
  the entry here.

## [0.1.0] - 2026-04-07

### Added

- Initial release: `cldc` CLI with commands `compile`, `doctor`, `check`,
  `ci`, `explain`, `fix`.
- Rule kinds: `deny_write`, `require_read`, `require_command`,
  `couple_change`.
- Modes: `observe`, `warn`, `block`, `fix`.
- Versioned JSON artifacts: policy lockfile, check report, fix plan, each
  with `$schema` and `format_version`.
- Git-aware CI entrypoints: staged and base/head diff evaluation.
- Deterministic source discovery and SHA-256 `source_digest`.

[Unreleased]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/AbdelStark/claude-md-compiler/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/AbdelStark/claude-md-compiler/releases/tag/v0.1.0
