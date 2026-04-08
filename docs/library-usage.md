# Library Usage

`cldc` is published as the [`claude-md-compiler`](https://pypi.org/project/claude-md-compiler/)
package and is a typed Python library in addition to the `cldc` CLI. The
package ships a `py.typed` marker so downstream type checkers (mypy, pyright,
pyre) pick up the inline annotations.

This document is the library reference. It is intentionally separate from the
CLI reference in [`README.md`](../README.md) so embedders, harness authors, and
test-suite integrators can read just the surface they need.

> The CLI is implemented as a thin shell over this same surface. Anything you
> can do at the command line, you can do programmatically — and vice versa.

## Table of contents

- [Installation](#installation)
- [Stable import paths](#stable-import-paths)
- [End-to-end example](#end-to-end-example)
- [Compiling policy](#compiling-policy)
- [Doctoring a repo](#doctoring-a-repo)
- [Evaluating evidence](#evaluating-evidence)
- [Loading evidence payloads](#loading-evidence-payloads)
- [Git-derived evidence](#git-derived-evidence)
- [Saved reports](#saved-reports)
- [Building remediation plans](#building-remediation-plans)
- [Working with bundled presets](#working-with-bundled-presets)
- [Scaffolding a fresh repo](#scaffolding-a-fresh-repo)
- [Hook generation and installation](#hook-generation-and-installation)
- [Typed exceptions](#typed-exceptions)
- [Logging](#logging)
- [JSON schemas and versioning](#json-schemas-and-versioning)
- [Determinism guarantees](#determinism-guarantees)

## Installation

```bash
# As a CLI tool (recommended)
uv tool install claude-md-compiler
pipx install claude-md-compiler

# As a library dependency
uv add claude-md-compiler
pip install claude-md-compiler
```

`cldc` requires Python 3.11+. The only runtime dependencies are `PyYAML` and
`textual` (the latter only used for the optional `cldc tui` command).

## Stable import paths

Every public symbol lives at one canonical import path. Re-exports are kept
intentionally narrow to avoid creating second-order coupling between modules.

```python
from cldc import __version__

# Compiler & doctor
from cldc.compiler.policy_compiler import (
    compile_repo_policy,
    doctor_repo_policy,
    CompiledPolicy,
    DoctorReport,
    LOCKFILE_FORMAT_VERSION,
    LOCKFILE_SCHEMA,
)

# Ingest layer (rarely needed by embedders, but exposed)
from cldc.ingest.discovery import discover_policy_repo, DiscoveryResult, LOCKFILE_PATH
from cldc.ingest.source_loader import (
    load_policy_sources,
    PolicySource,
    SourceBundle,
    SOURCE_PRECEDENCE,
)

# Parser
from cldc.parser.rule_parser import (
    parse_rule_documents,
    ParsedPolicy,
    RuleDefinition,
    ALLOWED_RULE_KINDS,
    ALLOWED_MODES,
    REQUIRED_FIELDS_BY_KIND,
)

# Runtime
from cldc.runtime.evaluator import (
    check_repo_policy,
    CheckReport,
    Violation,
)
from cldc.runtime.events import (
    CommandResult,
    load_execution_inputs,
    load_execution_inputs_file,
    load_execution_inputs_text,
    ExecutionInputs,
    EMPTY_EXECUTION_INPUTS,
    ALLOWED_EVENT_KINDS,
)
from cldc.runtime.git import collect_git_write_paths
from cldc.runtime.reporting import (
    load_check_report,
    load_check_report_file,
    load_check_report_text,
    render_check_report,
)
from cldc.runtime.remediation import (
    build_fix_plan,
    render_fix_plan,
    FIX_PLAN_FORMAT_VERSION,
    FIX_PLAN_SCHEMA,
)
from cldc.runtime.report_schema import (
    CHECK_REPORT_FORMAT_VERSION,
    CHECK_REPORT_SCHEMA,
)
from cldc.runtime.claude_code_adapter import (
    ClaudeCodeClaimReport,
    ClaudeCodeCommandResult,
    ClaudeCodeSessionState,
    HookRuntimeResult,
    record_claude_claim,
    run_post_tool_use,
    run_post_tool_use_failure,
    run_pre_tool_use,
    run_session_end,
    run_session_start,
    run_stop,
    resolve_session_report_path,
)

# Hooks and onboarding
from cldc.runtime.hooks import (
    generate_hook,
    install_hook,
    HookArtifact,
    HookInstallReport,
    SUPPORTED_HOOK_KINDS,
    INSTALLABLE_HOOK_KINDS,
)
from cldc.scaffold import initialize_repo_policy, InitReport

# Bundled preset packs
from cldc.presets import (
    list_presets,
    load_preset,
    preset_path,
    PRESET_SOURCE_KIND,
    PresetNotFoundError,
)

# Typed exception hierarchy
from cldc.errors import (
    CldcError,            # base class — inherits from ValueError for back-compat
    LockfileError,
    EvidenceError,
    ReportError,
    PolicySourceError,
    PresetError,
    RuleValidationError,
    RepoBoundaryError,
    GitError,
)
```

## End-to-end example

The shortest viable round-trip: compile, evaluate, and act on the verdict.

```python
from pathlib import Path

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy

repo = Path(".")

# 1. Compile sources into .claude/policy.lock.json (deterministic, sorted JSON).
compiled = compile_repo_policy(repo)
print(f"compiled {compiled.rule_count} rules from {compiled.source_count} sources")

# 2. Evaluate runtime evidence against the lockfile.
report = check_repo_policy(
    repo,
    read_paths=["docs/spec.md"],
    write_paths=["src/main.py"],
    commands=["pytest -q"],
    claims=["ci-green"],
)

# 3. Branch on the decision.
if report.decision == "block":
    for violation in report.violations:
        print(f"[{violation.mode}] {violation.rule_id}: {violation.message}")
        print(f"  next: {violation.recommended_action}")
    raise SystemExit(2)
```

## Compiling policy

`compile_repo_policy(repo_root)` walks up from `repo_root` (any path inside the
repo works), discovers the policy sources, parses them, and writes
`.claude/policy.lock.json`. It returns a `CompiledPolicy` dataclass and never
mutates anything outside `.claude/`.

```python
from cldc.compiler.policy_compiler import compile_repo_policy

compiled = compile_repo_policy("./tests/fixtures/repo_a")

compiled.repo_root          # absolute path string
compiled.lockfile_path      # ".claude/policy.lock.json"
compiled.compiler_version   # semver string from cldc.__version__
compiled.format_version     # "1"
compiled.source_digest      # SHA-256 hex of the canonicalized source bundle
compiled.default_mode       # "warn" by default
compiled.rule_count
compiled.source_count
compiled.source_paths       # ordered list of source paths (in load order)
compiled.warnings           # discovery warnings the compile suppressed
compiled.discovery          # full DiscoveryResult dict

compiled.to_dict()          # JSON-serializable representation
```

The lockfile is byte-stable for the same inputs: keys are sorted, lists keep
insertion order, and the SHA-256 digest is computed over a canonicalized
source bundle. Two machines compiling the same sources produce identical
files.

## Doctoring a repo

`doctor_repo_policy(repo_root)` returns a `DoctorReport` describing discovery
state, parser health, and lockfile freshness without rewriting anything. It is
the safe operation to run on suspect repos.

```python
from cldc.compiler.policy_compiler import doctor_repo_policy

report = doctor_repo_policy("./my-repo")

report.discovered          # bool
report.source_count
report.rule_count
report.default_mode        # str | None
report.source_digest       # str | None
report.lockfile_exists
report.lockfile_schema     # str | None
report.lockfile_format_version
report.lockfile_source_digest
report.warnings            # list[str]
report.errors              # list[str] — non-empty means the repo is broken
report.next_action         # str | None — actionable hint for the operator
```

`doctor_repo_policy` never raises on a malformed repo; it captures the failure
in `report.errors` instead. Programmer errors (e.g. `AttributeError`) still
propagate so they surface in tests.

## Evaluating evidence

`check_repo_policy(repo_root, **evidence)` is the pure-function judge. It
loads the lockfile, validates freshness against the current sources, and
evaluates evidence against every rule.

```python
from cldc.runtime.evaluator import check_repo_policy

report = check_repo_policy(
    "./my-repo",
    read_paths=["docs/spec.md"],
    write_paths=["src/main.py", "tests/test_main.py"],
    commands=["pytest -q"],
    claims=["qa-reviewed"],
)

report.ok                          # True for pass / warn, False for block
report.decision                    # "pass" | "warn" | "block"
report.summary
report.next_action                 # str | None
report.inputs                      # normalized inputs (dict[str, list[str]])
report.violation_count
report.blocking_violation_count
report.violations                  # list[Violation]
```

`Violation` carries the full structured context for an explainable failure:

```python
violation.rule_id
violation.kind                     # "deny_write" | "require_read" | ...
violation.mode                     # effective mode after default
violation.message                  # author-supplied
violation.explanation              # generated, plain English
violation.recommended_action       # generated, prescriptive
violation.matched_paths            # list[str] — what triggered the rule
violation.matched_commands
violation.matched_claims
violation.required_paths           # list[str] — what was missing
violation.required_commands
violation.required_claims
violation.source_path              # rule provenance
violation.source_block_id
```

Path normalization rejects any path that resolves outside the repo root,
raising `RepoBoundaryError`. Paths can be passed repo-relative or absolute.

## Loading evidence payloads

`load_execution_inputs(payload)` validates and normalizes a JSON evidence
document. It accepts both the bulk-list shape and a list of typed events:

```python
from cldc.runtime.events import (
    load_execution_inputs,
    load_execution_inputs_file,
    load_execution_inputs_text,
)

inputs = load_execution_inputs({
    "read_paths": ["docs/spec.md"],
    "write_paths": ["src/main.py"],
    "commands": ["pytest -q"],
    "command_results": [
        {"command": "pytest -q", "outcome": "success"},
    ],
    "claims": ["qa-reviewed"],
    "events": [
        {"kind": "read", "path": "docs/extra.md"},
        {"kind": "write", "path": "src/util.py"},
        {"kind": "command", "command": "ruff check", "outcome": "success"},
        {"kind": "claim", "claim": "ci-green"},
    ],
})

# load from disk
inputs = load_execution_inputs_file(".cldc-events.json")

# load from a text payload (e.g. stdin)
inputs = load_execution_inputs_text(stdin_text, source="stdin")
```

`ExecutionInputs.merged_with(other)` returns a new `ExecutionInputs` with
fields concatenated in order — no deduplication. Use it to merge a JSON
payload with explicit per-flag evidence the way the CLI does.

Use `CommandResult` when a caller needs outcome-aware command evidence:

```python
from cldc.runtime.events import CommandResult

report = check_repo_policy(
    "./my-repo",
    write_paths=["src/main.py"],
    command_results=[CommandResult(command="pytest -q", outcome="success")],
)
```

The full payload can be passed straight to `check_repo_policy` via
`event_payload=...`:

```python
report = check_repo_policy(
    "./my-repo",
    write_paths=["src/main.py"],
    event_payload={
        "read_paths": ["docs/spec.md"],
        "claims": ["ci-green"],
    },
)
```

## Git-derived evidence

`collect_git_write_paths` runs `git diff` against either the staging area or a
base/head range and returns the changed paths plus deterministic provenance
metadata that can be embedded in a check report.

```python
from cldc.runtime.git import collect_git_write_paths

# Staged changes (mirrors `cldc ci --staged`)
paths, metadata = collect_git_write_paths("./my-repo", staged=True)

# Range diff (mirrors `cldc ci --base origin/main --head HEAD`)
paths, metadata = collect_git_write_paths(
    "./my-repo",
    base="origin/main",
    head="HEAD",
)

metadata = {
    "mode": "range",
    "base": "origin/main",
    "head": "HEAD",
    "git_command": ["git", "diff", "--name-only", "origin/main...HEAD"],
    "write_path_count": len(paths),
}
```

`collect_git_write_paths` raises `GitError` on invalid flag combinations,
git command failures, or a missing `git` binary on `PATH`.

## Saved reports

A check report can be saved as JSON, then loaded later for explanation or
remediation without re-running the evaluator. Use this when CI stores the
report as a build artifact and a downstream job renders it.

```python
import json

from cldc.runtime.reporting import (
    load_check_report,
    load_check_report_file,
    render_check_report,
)

# From a Python dict (e.g. CheckReport.to_dict())
normalized = load_check_report(report.to_dict())

# From a JSON file
normalized = load_check_report_file("artifacts/policy-report.json")

# Render
print(render_check_report(normalized, format="text"))
print(render_check_report(normalized, format="markdown"))
```

`load_check_report_*` functions raise `ReportError` on schema drift, format
version mismatches, or malformed payloads.

## Building remediation plans

`build_fix_plan(report_payload)` produces a deterministic remediation plan
from a check report. The plan is purely advisory — `cldc` never executes
remediations on its own.

```python
from cldc.runtime.remediation import build_fix_plan, render_fix_plan

plan = build_fix_plan(report.to_dict())

plan["$schema"]                # "https://cldc.dev/schemas/policy-fix-plan/v1"
plan["format_version"]         # "1"
plan["decision"]
plan["remediation_count"]
plan["next_action"]
for remediation in plan["remediations"]:
    remediation["rule_id"]
    remediation["priority"]    # "blocking" | "non-blocking"
    remediation["steps"]       # list[str]
    remediation["files_to_inspect"]
    remediation["suggested_commands"]
    remediation["forbidden_commands"]
    remediation["suggested_claims"]
    remediation["can_autofix"] # always False today; reserved for v2

print(render_fix_plan(plan, format="markdown"))
```

`render_fix_plan` accepts either a fresh check-report payload or an
already-built fix plan; it normalizes whichever it receives.

## Working with bundled presets

```python
from cldc.presets import list_presets, load_preset, preset_path

for preset in list_presets():
    print(preset.name, preset.path)

raw_yaml = load_preset("default")
on_disk_path = preset_path("strict")
```

A repo references a preset from `.claude-compiler.yaml`:

```yaml
extends:
  - default
  - docs-sync
```

The compiler resolves preset names through the same loader API and embeds
their content into the source bundle as a `preset` source kind, so the
lockfile's `source_digest` covers the preset content too.

## Scaffolding a fresh repo

`initialize_repo_policy(target, presets=...)` is the programmatic equivalent
of `cldc init`. It writes `.claude-compiler.yaml` (with `extends:` and an
empty `rules:` list) and a stub `CLAUDE.md` if none exists.

```python
from cldc.scaffold import initialize_repo_policy

report = initialize_repo_policy("./new-repo", presets=["default", "strict"])

report.repo_root
report.presets
report.created       # ['.claude-compiler.yaml', 'CLAUDE.md']
report.updated       # only when force=True overwrote a file
report.skipped       # ['CLAUDE.md'] if it already existed
report.next_action   # actionable hint pointing at `cldc compile`
```

## Hook generation and installation

```python
from cldc.runtime.hooks import (
    generate_hook,
    install_hook,
    SUPPORTED_HOOK_KINDS,
    INSTALLABLE_HOOK_KINDS,
)

# Pure: just returns the script content + metadata
artifact = generate_hook("git-pre-commit")
print(artifact.content)

# Side-effecting: writes .git/hooks/pre-commit
report = install_hook("git-pre-commit", "./my-repo", force=False)
report.action       # "created" | "updated"
report.target_path  # ".git/hooks/pre-commit"
report.executable   # True
```

`generate_hook("claude-code")` returns a `.claude/settings.json` snippet that
wires Claude Code's lifecycle hooks into `cldc`'s stateful session adapter:

- `SessionStart` initializes machine-local state for the repo/session.
- `PreToolUse` blocks true write preconditions such as blocking
  `deny_write` and `require_read`.
- `PostToolUse` records successful `Read`, `Edit`, `Write`, `MultiEdit`, and
  `Bash` evidence, persists the latest report, and returns JSON hook feedback
  Claude can actually process.
- `PostToolUseFailure` records failed commands separately so only successful
  commands satisfy `require_command_success`.
- `Stop` evaluates the full accumulated session and can emit a blocking
  payload while workflow invariants remain unmet.
- `SessionEnd` deletes mutable session state but leaves the latest saved
  report on disk.

The adapter persists state under `~/.claude/cldc/projects/<repo-hash>/...` by
default. Set `CLDC_CLAUDE_STATE_DIR` to override that root during tests or
custom harness runs. Claims are explicit because Claude Code has no native
claim tool event:

```python
from cldc.runtime.claude_code_adapter import record_claude_claim

claim_report = record_claude_claim("./my-repo", "ci-green", session_id="session-123")
print(claim_report.claim_count)
```

The runtime helpers are also available directly for embedders that want to
drive the lifecycle themselves instead of shelling out through `cldc hook
runtime`. The generated settings snippet is still intentionally generate-only;
merging it into an existing settings file is the operator's job.

To hand the saved hook report into the normal report/rendering pipeline:

```python
from cldc.runtime.claude_code_adapter import resolve_session_report_path
from cldc.runtime.reporting import load_check_report_file

report_path = resolve_session_report_path("./my-repo")
report_payload = load_check_report_file(report_path)
```

## Typed exceptions

Every library error inherits from `CldcError`, which itself inherits from
`ValueError` so legacy `except ValueError` consumers keep working. Catch the
specific subclass in new code to branch on failure modes:

| Exception | Raised when |
| --- | --- |
| `PolicySourceError` | Malformed policy source files (`CLAUDE.md`, `.claude-compiler.yaml`, `policies/*.yml`). |
| `RuleValidationError` | A rule document fails validation (missing kind, duplicate id, …). |
| `LockfileError` | The compiled lockfile is malformed, stale, schema-drifted, or contains an unsupported rule kind. |
| `EvidenceError` | An execution-input / event payload fails validation. |
| `ReportError` | A saved check report or fix plan fails validation. |
| `PresetError` / `PresetNotFoundError` | A bundled preset cannot be loaded or resolved. |
| `RepoBoundaryError` | A runtime evidence path resolves outside the repo root. |
| `GitError` | A `git` invocation or argument combination failed during `cldc ci`. |

`FileNotFoundError` is reused (instead of being subclassed) for missing repo
paths and missing artifacts so the standard library predicate
`isinstance(exc, FileNotFoundError)` keeps working.

## Logging

`cldc` is silent by default. Importing the package attaches a `NullHandler`
to the `cldc` logger so embedding the library in another application never
prints anything unexpected.

```python
import logging

logging.getLogger("cldc").setLevel(logging.DEBUG)
logging.getLogger("cldc").addHandler(logging.StreamHandler())
```

The CLI calls `cldc._logging.configure_cli_logging(verbose=..., quiet=...)`
to attach a stderr handler with the level derived from `--verbose`/`--quiet`.

## JSON schemas and versioning

Three JSON artifacts are versioned contracts. Each carries a `$schema` URI
and a string `format_version` so consumers can detect drift.

| Artifact | `$schema` constant | `format_version` constant |
| --- | --- | --- |
| Policy lockfile | `LOCKFILE_SCHEMA` (`https://cldc.dev/schemas/policy-lock/v1`) | `LOCKFILE_FORMAT_VERSION` (`"1"`) |
| Check report | `CHECK_REPORT_SCHEMA` (`https://cldc.dev/schemas/policy-report/v1`) | `CHECK_REPORT_FORMAT_VERSION` (`"1"`) |
| Fix plan | `FIX_PLAN_SCHEMA` (`https://cldc.dev/schemas/policy-fix-plan/v1`) | `FIX_PLAN_FORMAT_VERSION` (`"1"`) |

Any breaking change to the shape of these artifacts requires a major version
bump on both the schema URI (`/v2`) and the `format_version` string. RFC-style
specifications for these contracts live under
[`docs/rfcs/`](./rfcs/).

## Determinism guarantees

- The compiled lockfile is byte-stable for the same inputs (sorted keys,
  stable list ordering, SHA-256 source digest).
- `CheckReport.to_dict()` always emits the same key set; absent-by-default
  values are zero-length lists, never `None`.
- Fix plans are computed from the report alone and contain no clock or
  environment data.
- The library never makes network calls. All I/O is local file I/O with
  explicit `encoding="utf-8"`.
- Path normalization rejects any input path that escapes the discovered
  repo root.
- Unsupported rule kinds raise `LockfileError` rather than degrading to a
  silent pass.
