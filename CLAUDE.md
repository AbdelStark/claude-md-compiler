<identity>
cldc (claude-md-compiler) — A policy compiler that transforms CLAUDE.md into enforceable, versioned repo policy via .claude/policy.lock.json.
</identity>

<stack>

| Layer       | Technology | Version | Notes                          |
|-------------|-----------|---------|--------------------------------|
| Language    | Python    | >=3.11  | Type hints used throughout     |
| Build       | setuptools| —       | Via pyproject.toml             |
| Dependency  | PyYAML    | >=6.0   | Only runtime dependency        |
| Testing     | pytest    | >=8.0   | Dev dependency only            |
| Entry point | cldc CLI  | 0.1.0   | `cldc compile [repo] [--json]` |

Package manager: pip (no lockfile — use `pip install -e ".[dev]"` for editable install).
</stack>

<structure>
src/cldc/                # Main package
├── __init__.py          # Version string ("0.1.0")
├── cli/
│   └── main.py          # CLI entry point — argparse, exit codes 0/1/2
├── compiler/
│   └── policy_compiler.py  # Orchestrates ingest→parse→lockfile generation
├── ingest/
│   └── source_loader.py    # Discovers & loads CLAUDE.md, .claude-compiler.yaml, policies/*.yml
├── parser/
│   └── rule_parser.py      # Validates rule YAML, merges sources, detects duplicates
└── policy/
    └── __init__.py          # Empty — future validator/enforcement logic

tests/                   # All tests [agent: create/modify]
├── fixtures/repo_a/     # Test fixture repo with CLAUDE.md + config + policy file
├── test_cli.py
├── test_compiler.py
├── test_rule_parser.py
├── test_source_loader.py
└── test_validation.py

docs/                    # [agent: READ ONLY unless extending RFCs]
├── specs/product-spec.md
└── rfcs/CLDC-0001..0012  # 12 RFCs defining phased implementation
</structure>

<commands>

| Task            | Command                          | Notes                              |
|-----------------|----------------------------------|------------------------------------|
| Install (dev)   | pip install -e ".[dev]"          | Editable install with pytest       |
| Test            | pytest                           | Runs 11 tests, ~1s                 |
| Test (verbose)  | pytest -v                        | Show individual test names         |
| Test (single)   | pytest tests/test_X.py -k "name" | Filter by test name                |
| Run CLI         | cldc compile tests/fixtures/repo_a | Compile test fixture             |
| Run CLI (JSON)  | cldc compile tests/fixtures/repo_a --json | JSON output mode          |
| Type check      | python -m py_compile src/cldc/**/*.py | Basic syntax validation     |
</commands>

<conventions>
<code_style>
  Naming: snake_case for functions/variables/modules, PascalCase for classes, UPPER_SNAKE for constants.
  Files: snake_case.py, one module per concern.
  Imports: stdlib → third-party (yaml) → local (cldc.*). Absolute imports within package.
  Classes: dataclasses or plain classes with __init__. No ORMs, no metaclass magic.
  Strings: Double quotes for user-facing messages, either style for internal.
</code_style>

<patterns>
  <do>
    — Use dataclass-style objects for structured data (PolicySource, RuleDefinition, etc.)
    — Return structured objects from functions, not raw dicts
    — Raise ValueError/TypeError for validation failures with descriptive messages
    — Keep functions pure where possible — source_loader returns SourceBundle, parser returns ParsedPolicy
    — Maintain deterministic output — sort globs, stable ordering, reproducible lockfiles
    — Include provenance tracking — every rule knows its source file and line
    — Write tests for both happy path and error cases
  </do>
  <dont>
    — Don't use external dependencies beyond PyYAML — keep the core minimal
    — Don't use print() for output — use json.dumps for structured output, sys.stderr for errors
    — Don't mutate input data — create new objects
    — Don't hardcode paths — use os.path.join and repo_root-relative resolution
    — Don't swallow exceptions — let validation errors propagate with context
  </dont>
</patterns>

<commit_conventions>
  Format: imperative mood, lowercase start, no period. Example: "add validator engine for block mode"
  Keep commits focused — one logical change per commit.
</commit_conventions>
</conventions>

<architecture_context>
The compiler follows a 3-stage pipeline:

  1. INGEST (source_loader.py): Discover sources → extract inline ```cldc``` blocks → return SourceBundle
  2. PARSE (rule_parser.py): Validate each rule → merge across sources → detect conflicts → return ParsedPolicy
  3. COMPILE (policy_compiler.py): Generate .claude/policy.lock.json with metadata, version, rule list

Source precedence: CLAUDE.md → .claude-compiler.yaml → policies/*.yml (all sorted deterministically).

Rule kinds: require_read, deny_write, require_command, couple_change
Enforcement modes: observe, warn, block, fix (default: warn)

Lockfile schema (policy.lock.json):
  - compiler_version: string
  - format_version: "1"
  - generated_at: ISO timestamp
  - repo_root: absolute path
  - rule_count: int
  - rules: list of rule dicts with full provenance
</architecture_context>

<implementation_status>
Phase 1 COMPLETE (CLDC-0001, 0002, 0003):
  ✓ Source loader with precedence and inline block extraction
  ✓ Rule parser with schema validation and duplicate detection
  ✓ Compiler generating policy.lock.json
  ✓ CLI compile command
  ✓ 11 tests

Phase 2 NOT STARTED (next priorities):
  — CLDC-0004: Repo scanner and topology index
  — CLDC-0005: Execution event model
  — CLDC-0006: Validator engine
  — CLDC-0007: Enforcement modes

Phase 3 NOT STARTED:
  — CLDC-0008 through CLDC-0012 (fix suggestions, CLI expansion, CI integration, reports, presets)
</implementation_status>

<workflows>
<new_feature>
  1. Read the relevant RFC in docs/rfcs/ — it defines the contract and acceptance criteria
  2. Create new module in appropriate src/cldc/ subdirectory
  3. Implement following the pipeline pattern (ingest → parse → compile → validate)
  4. Write tests in tests/ — cover happy path + error cases + edge cases from RFC
  5. Run `pytest` — all must pass
  6. Verify no regressions in existing tests
  7. Commit with descriptive message
</new_feature>

<bug_fix>
  1. Write a failing test that reproduces the bug
  2. Fix the code
  3. Run `pytest` — all must pass including the new test
  4. Commit
</bug_fix>

<adding_rule_kind>
  1. Add kind to ALLOWED_KINDS in src/cldc/parser/rule_parser.py
  2. Add validation logic for kind-specific required fields
  3. Add test cases in tests/test_rule_parser.py and tests/test_validation.py
  4. Update test fixture if needed (tests/fixtures/repo_a/)
  5. Run `pytest`
</adding_rule_kind>
</workflows>

<boundaries>
<forbidden>
  DO NOT modify:
  — docs/rfcs/*.md (RFCs are frozen specifications — reference only)
  — docs/specs/product-spec.md (product spec is reference material)
  — tests/fixtures/ data in ways that break existing tests
</forbidden>

<gated>
  Modify ONLY with explicit approval:
  — pyproject.toml (dependency or config changes)
  — src/cldc/__init__.py version string
  — Lockfile format_version in policy_compiler.py
</gated>
</boundaries>
