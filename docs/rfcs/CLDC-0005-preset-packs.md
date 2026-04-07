# CLDC-0005: Preset packs

- **Status**: Frozen
- **Created**: 2026-04-07
- **Supersedes**: —
- **Superseded by**: —

## Abstract

`cldc` ships with a small set of opinionated *preset policy packs*
that any repository can pull into its compiled lockfile via an
`extends:` directive in `.claude-compiler.yaml`. This RFC freezes the
on-disk layout of preset packs, the `extends:` resolution rules, the
`preset` source kind that the compiler emits, and the way preset
sources interact with lockfile freshness checks.

## Motivation

The same handful of guardrails — "do not write to generated/", "rerun
the install command after a manifest change", "tests must move with
source" — show up in almost every repo we want to enforce policy on.
Without preset packs, every repo has to copy-paste them into its own
`policies/` directory, which guarantees drift. Preset packs let us
ship one curated copy that consumers `extends:` into their own
configuration without giving up the ability to add their own rules
on top.

## Specification

### File layout

Preset packs live under `src/cldc/presets/packs/` inside the installed
`cldc` package. Each pack is exactly one YAML file.

- The filename is `<name>.yml`. The pack's name is the filename stem.
- Names must consist of lowercase ASCII letters, digits, and hyphens
  (`[a-z0-9-]+`). The loader does not enforce a regex but every
  bundled pack honors this convention and tooling assumes it.
- The file extension must be `.yml` exactly. `.yaml` is not
  recognized.
- The file body is a normal `cldc` rule document: a top-level mapping
  with a `rules:` key whose value is a list of rule objects, plus an
  optional leading comment block describing the pack.

This layout is implemented by `src/cldc/presets/loader.py`:

```python
PRESET_SOURCE_KIND = "preset"
_PACKS_DIR = Path(__file__).parent / "packs"
_PRESET_SUFFIX = ".yml"
```

### Loader API

`src/cldc/presets/loader.py` exposes the following surface, which is
the only allowed way to discover or read preset content:

| Symbol                  | Purpose                                                                            |
|-------------------------|------------------------------------------------------------------------------------|
| `PRESET_SOURCE_KIND`    | The string `"preset"`. Used wherever a `PolicySource.kind` is expected.            |
| `PresetMetadata`        | Frozen dataclass with `name` and `path` fields, plus `to_dict()`.                  |
| `PresetNotFoundError`   | Subclass of `LookupError`. Raised when a requested name is not bundled.            |
| `list_presets()`        | Returns every bundled preset as a sorted list of `PresetMetadata`.                 |
| `preset_path(name)`     | Returns the resolved `Path` for a preset, or raises `PresetNotFoundError`.         |
| `load_preset(name)`     | Returns the raw UTF-8 YAML text of a preset, or raises `PresetNotFoundError`.      |

`list_presets()` sorts by name so the output is deterministic across
machines.

### `extends:` resolution

The `extends:` directive lives at the top of `.claude-compiler.yaml`
and is parsed by `_load_preset_names` in
`src/cldc/ingest/source_loader.py`:

- The value must be a list of non-empty strings.
- Each string is a preset name. The loader accepts both the bare
  spelling (`default`) and the explicitly prefixed spelling
  (`preset:default`). The prefix is the only namespace currently
  defined; future namespaces will require a superseding RFC.
- Whitespace is stripped from each entry. An empty entry, or a
  prefix with no name after it, is a hard error.
- Duplicate names — including duplicates after stripping the prefix —
  are silently deduplicated.
- An unknown name raises `ValueError` with a message that lists every
  bundled preset.

Example `.claude-compiler.yaml`:

```yaml
default_mode: warn
extends:
  - default
  - preset:strict
include:
  - policies/*.yml
```

### Source ordering and merging

`SOURCE_PRECEDENCE` in `src/cldc/ingest/source_loader.py` is:

```python
["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]
```

This places `preset` strictly **between** `compiler_config` and
`policy_file`. The compiler emits sources in this order, the lockfile
records them in this order, and the source digest hashes them in this
order. Reordering preset sources relative to user content is therefore
impossible without re-compiling.

When the compiler walks the four ingestion stages it produces, in
order, for each repository:

1. The repository's `CLAUDE.md` (if any) and every inline `cldc` block
   inside it.
2. The repository's `.claude-compiler.yaml` (if any).
3. The presets named in `extends:`, in the order they appear in
   `extends:` after deduplication.
4. The policy fragments matched by the configured `include:` globs.

Every source ends up in the lockfile's `sources` array. Every rule
defined in any of those sources ends up in the lockfile's `rules`
array.

### Preset source provenance

Each preset is recorded as a `PolicySource` with:

| Field        | Value                                                                          |
|--------------|--------------------------------------------------------------------------------|
| `kind`       | `"preset"` (`PRESET_SOURCE_KIND`)                                              |
| `path`       | `"preset:<name>"` — the literal string, not a filesystem path                  |
| `content`    | The verbatim YAML body of the preset file                                      |
| `block_id`   | The preset name                                                                |
| `line_start` | `null`                                                                         |

The `preset:` path prefix is the way every other component recognizes
that a source lives inside the installed `cldc` package rather than
inside the repo. Consumers must treat any `path` whose value starts
with `"preset:"` as opaque and must not try to resolve it as a
filesystem path.

### Duplicate rule IDs

Rule IDs must be unique across the entire lockfile. The parser
(`parse_rule_documents` in `src/cldc/parser/rule_parser.py`) tracks a
`seen_ids` set across every source — including preset sources — and
raises `ValueError` on the first collision. There is no override or
suppression mechanism. Pack authors must therefore namespace their
IDs (every bundled pack uses the prefix `preset-<pack-name>-`).

### Lockfile freshness exemption

`_validate_lockfile_freshness` in `src/cldc/runtime/evaluator.py`
checks the modification time of every repo-local source against the
lockfile's mtime, but it skips any source whose `path` starts with
`"preset:"`. The reason is mechanical: preset sources live inside the
installed `cldc` package, not inside the repo, so the repo-relative
mtime check would dereference a path that does not exist on the
checking machine. Instead, preset content is covered by the
`source_digest` check from CLDC-0001, which hashes the verbatim
content of every source regardless of where it came from. Upgrading
`cldc` to a version with different preset content therefore changes
the digest and forces `cldc compile` to be re-run.

### Bundled packs

As of version 0.1.1, three packs ship with `cldc`:

| Name        | One-line description                                                                                  |
|-------------|-------------------------------------------------------------------------------------------------------|
| `default`   | Baseline guardrails: deny writes to generated/, dist/, build/; warn when manifests change without an install command. |
| `strict`    | Source changes must be coupled with tests, must read architecture context first, and require a `ci-green` claim. |
| `docs-sync` | Couple user-facing surface changes with README/docs/ updates and version bumps with CHANGELOG entries. |

The exact rule contents live in `src/cldc/presets/packs/` and are
visible via `cldc preset list` and `cldc preset show <name>`.

### Adding a new preset

1. Drop a new YAML file under `src/cldc/presets/packs/<name>.yml`
   following the naming and content rules above.
2. Namespace every rule ID with `preset-<name>-` to avoid collisions
   across packs and with user rules.
3. Add a `tests/test_presets.py` test that asserts
   `list_presets()` includes the new pack and that
   `parse_rule_documents` accepts its content.
4. Mention the pack in this RFC's "Bundled packs" table in the same
   PR. The "Bundled packs" list is part of this RFC's normative
   surface only insofar as it must enumerate the packs that ship; the
   one-line descriptions are advisory.

## Compatibility

A consumer at the policy lockfile schema **must**:

- Recognize `preset` as a value of `PolicySource.kind` and treat the
  source's `path` (`preset:<name>`) as opaque.
- Skip the repo-local mtime freshness check for any source with a
  `preset:` path.
- Refuse to load any `.claude-compiler.yaml` whose `extends:` value is
  not a list of non-empty strings.
- Refuse to load a configuration that names an unknown preset.

A consumer that does not understand presets at all (for example, an
older `cldc` version) will fail closed when its lockfile validator
sees the `"preset"` entry in `source_precedence` or a `preset:`
prefixed source `path` it cannot resolve. This is the intended
behavior: preset support is part of the v1 lockfile, and refusing to
parse a v1 lockfile from an older version is the contract.

## Validation

Test surface that locks in this contract today:

- `tests/test_presets.py` — preset discovery, naming, and content
  validity.
- `tests/test_source_loader.py` — `extends:` parsing, prefix handling,
  deduplication, unknown-name rejection.
- `tests/test_runtime.py` — preset sources are skipped by the mtime
  freshness check but still covered by the source digest.
- `tests/test_cli.py` — `cldc preset list` and `cldc preset show`
  command output.

## Reference

- `src/cldc/presets/loader.py` — `PRESET_SOURCE_KIND`,
  `PresetMetadata`, `PresetNotFoundError`, `list_presets`,
  `preset_path`, `load_preset`.
- `src/cldc/presets/packs/default.yml`,
  `src/cldc/presets/packs/strict.yml`,
  `src/cldc/presets/packs/docs-sync.yml` — bundled preset content.
- `src/cldc/ingest/source_loader.py` — `SOURCE_PRECEDENCE`,
  `_load_preset_names`, `_load_preset_sources`, `load_policy_sources`.
- `src/cldc/parser/rule_parser.py` — duplicate-id enforcement.
- `src/cldc/runtime/evaluator.py` — `_validate_lockfile_freshness`
  preset skip.
- `src/cldc/cli/main.py` — `cldc preset list` and `cldc preset show`.
