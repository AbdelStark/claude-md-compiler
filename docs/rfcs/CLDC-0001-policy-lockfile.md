# CLDC-0001: Policy lockfile

- **Status**: Frozen
- **Created**: 2026-04-07
- **Supersedes**: —
- **Superseded by**: —

## Abstract

`cldc compile` writes a single JSON artifact, `.claude/policy.lock.json`,
that captures every policy source it discovered, the rules it parsed out
of those sources, and a content digest that pins the lockfile to its
inputs. Every other `cldc` command — `check`, `ci`, `explain`, `fix`,
`doctor` — refuses to act on a lockfile whose schema, format, or digest
does not line up with the current sources. This RFC freezes the on-disk
shape of that lockfile.

## Motivation

The lockfile is the only thing the runtime trusts. If we let it drift
silently — newer compiler writes a key the older runtime ignores, or an
edited source produces the same lockfile — the entire enforcement story
collapses into "trust the latest binary." Pinning the schema and the
digest pushes drift detection into the loader so consumers fail loudly
instead of guessing.

## Specification

### Identity

- `$schema`: `https://cldc.dev/schemas/policy-lock/v1` (string, required).
  Defined as `LOCKFILE_SCHEMA` in `src/cldc/compiler/policy_compiler.py`.
- `format_version`: `"1"` (string, required). Defined as
  `LOCKFILE_FORMAT_VERSION` in the same module.
- `compiler_version`: the `cldc` package version that wrote the file
  (string, required). Sourced from `cldc.__version__`.

### Top-level keys

The payload is a JSON object built by `_build_lock_payload` in
`src/cldc/compiler/policy_compiler.py`. Every key listed here is
required and must appear in every well-formed lockfile.

| Key                  | Type                | Notes                                                                                          |
|----------------------|---------------------|------------------------------------------------------------------------------------------------|
| `$schema`            | string              | Pinned to the value above.                                                                     |
| `format_version`     | string              | Pinned to `"1"`.                                                                               |
| `compiler_version`   | string              | The compiler that wrote the artifact.                                                          |
| `repo_root`          | string              | Absolute path to the repo root that produced this lockfile.                                    |
| `default_mode`       | string              | One of `observe`, `warn`, `block`, `fix`. Drives any rule that omits an explicit `mode`.       |
| `rule_count`         | integer             | Must equal `len(rules)`. Loaders refuse the lockfile if this drifts.                           |
| `source_count`       | integer             | Must equal `len(sources)`.                                                                     |
| `source_digest`      | string              | 64-character lowercase SHA-256 hex. See "Source digest" below.                                 |
| `source_precedence`  | array of strings    | Frozen ordered list. See below.                                                                |
| `discovery`          | object              | Snapshot of `DiscoveryResult.to_dict()` from `src/cldc/ingest/discovery.py`.                   |
| `sources`            | array of objects    | Every parsed source, in `source_precedence` order.                                             |
| `rules`              | array of objects    | Every parsed rule, in source-then-document order.                                              |

### `source_precedence`

```json
["claude_md", "inline_block", "compiler_config", "preset", "policy_file"]
```

This list is exported as `SOURCE_PRECEDENCE` from
`src/cldc/ingest/source_loader.py`. Loaders use it both to iterate
sources deterministically and as input to the `source_digest` calculation
described below. The list must appear verbatim — adding or reordering
entries is a `$schema` break.

### `sources[]` shape

Each entry is the `to_dict()` of a `PolicySource` (see
`src/cldc/ingest/source_loader.py`):

| Key          | Type             | Notes                                                                                              |
|--------------|------------------|----------------------------------------------------------------------------------------------------|
| `kind`       | string           | One of the values in `source_precedence`.                                                          |
| `path`       | string           | Repo-relative POSIX path, except for presets which use `preset:<name>` (see CLDC-0005).            |
| `content`    | string           | Verbatim source text. Inline blocks contain only the body between the fences.                      |
| `block_id`   | string \| null   | For inline blocks: `<file>:<line>`. For presets: the preset name. Otherwise null.                  |
| `line_start` | integer \| null  | For inline blocks: 1-based line number of the opening fence. Otherwise null.                       |

### `rules[]` shape

Each entry is the `to_dict()` of a `RuleDefinition` (see
`src/cldc/parser/rule_parser.py`):

| Key                | Type                          | Notes                                                                                |
|--------------------|-------------------------------|--------------------------------------------------------------------------------------|
| `id`               | string                        | Unique across the whole lockfile. Duplicate IDs are a hard parse error.              |
| `kind`             | string                        | One of `deny_write`, `require_read`, `require_command`, `require_command_success`, `couple_change`, `require_claim`. |
| `message`          | string                        | Non-empty human-readable description.                                                |
| `mode`             | string \| null                | One of `observe`, `warn`, `block`, `fix`, or null to inherit `default_mode`.         |
| `paths`            | array of strings \| null      | Required for `deny_write`, `require_read`, `couple_change`.                          |
| `before_paths`     | array of strings \| null      | Required for `require_read`.                                                         |
| `when_paths`       | array of strings \| null      | Required for `require_command`, `require_command_success`, `couple_change`, `require_claim`.                    |
| `commands`         | array of strings \| null      | Required for `require_command` and `require_command_success`.                                                      |
| `claims`           | array of strings \| null      | Required for `require_claim` (see CLDC-0004).                                        |
| `source_path`      | string \| null                | Provenance: which source produced this rule.                                         |
| `source_block_id`  | string \| null                | Provenance for inline blocks and presets.                                            |

The required-field matrix is encoded in `REQUIRED_FIELDS_BY_KIND` in
`src/cldc/parser/rule_parser.py`. Any rule that omits a required field is
rejected at parse time, not at runtime.

### Source digest

`source_digest` is the lowercase SHA-256 hex of the canonical JSON
encoding of:

```json
{
  "source_precedence": ["claude_md", "inline_block", "compiler_config", "preset", "policy_file"],
  "sources": [<every source as PolicySource.to_dict(), in order>]
}
```

The canonical encoding is `json.dumps(..., sort_keys=True,
separators=(",", ":"))`. This is implemented as `_compute_source_digest`
in `src/cldc/compiler/policy_compiler.py` and is the only digest format
loaders accept. Any other key set, ordering, or whitespace produces a
different digest and the lockfile is rejected.

### Byte stability

`compile_repo_policy` writes the file with
`json.dumps(payload, indent=2, sort_keys=True) + "\n"` followed by a
single trailing newline, in UTF-8. Any well-formed lockfile must satisfy
the same shape so that two compiles of the same sources produce
byte-identical output. Pretty-printing, removing the trailing newline,
or omitting `sort_keys` is a contract break.

## Compatibility

A consumer at this `$schema` URL **must**:

- Reject the lockfile when `$schema` is missing or different.
- Reject the lockfile when `format_version` is missing or different.
- Reject the lockfile when `repo_root` does not match the discovered
  repository root for the consuming command.
- Reject the lockfile when `rule_count != len(rules)`.
- Reject the lockfile when `source_digest` is missing, not 64 lowercase
  hex characters, or does not match a fresh recomputation over the
  current sources.
- Refuse to silently degrade for any rule whose `kind` it does not
  recognize.

These rules are enforced by `_load_lockfile` and
`_validate_lockfile_freshness` in `src/cldc/runtime/evaluator.py`. The
text the consumer prints is not part of this contract; the rejection is.

A future format change that adds new optional keys with safe defaults
may bump `format_version` to `"2"` while keeping the `$schema` URL.
Renaming or repurposing any existing key requires a new `$schema` URL
and a superseding RFC.

## Validation

Test surface that locks in this contract today:

- `tests/test_compiler.py` — round-trip lockfile shape, byte stability,
  digest invariance, drift detection.
- `tests/test_runtime.py` — runtime rejection of stale, mismatched, and
  schema-drifted lockfiles.
- `tests/test_cli.py` — CLI exit-code mapping for `compile`, `doctor`,
  `check`, `ci`.

## Reference

- `src/cldc/compiler/policy_compiler.py` — `LOCKFILE_SCHEMA`,
  `LOCKFILE_FORMAT_VERSION`, `_build_lock_payload`,
  `_compute_source_digest`, `compile_repo_policy`,
  `_validate_existing_lockfile`.
- `src/cldc/ingest/source_loader.py` — `SOURCE_PRECEDENCE`,
  `PolicySource`, `load_policy_sources`.
- `src/cldc/parser/rule_parser.py` — `RuleDefinition`,
  `REQUIRED_FIELDS_BY_KIND`, `parse_rule_documents`.
- `src/cldc/runtime/evaluator.py` — `_load_lockfile`,
  `_validate_lockfile_freshness`.

## Appendix: minimal valid example

Abbreviated output of `cldc compile tests/fixtures/repo_a` with
`compiler_version`, `repo_root`, and the `discovery` block trimmed for
brevity:

```json
{
  "$schema": "https://cldc.dev/schemas/policy-lock/v1",
  "compiler_version": "0.2.0",
  "default_mode": "warn",
  "discovery": { "...": "DiscoveryResult.to_dict()" },
  "format_version": "1",
  "repo_root": "/abs/path/to/repo",
  "rule_count": 1,
  "rules": [
    {
      "before_paths": null,
      "claims": null,
      "commands": null,
      "id": "generated-lock",
      "kind": "deny_write",
      "message": "Do not touch generated files.",
      "mode": "block",
      "paths": ["generated/**"],
      "source_block_id": "CLAUDE.md:6",
      "source_path": "CLAUDE.md",
      "when_paths": null
    }
  ],
  "source_count": 1,
  "source_digest": "<sha256 hex>",
  "source_precedence": [
    "claude_md", "inline_block", "compiler_config", "preset", "policy_file"
  ],
  "sources": [
    {
      "block_id": "CLAUDE.md:6",
      "content": "rules:\n  - id: generated-lock\n    ...",
      "kind": "inline_block",
      "line_start": 6,
      "path": "CLAUDE.md"
    }
  ]
}
```
