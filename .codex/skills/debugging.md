---
name: debugging
description: Debugging and troubleshooting workflows for cldc. Activate when encountering errors, unexpected behavior, test failures, or when diagnosing issues in the compiler pipeline.
prerequisites: none
---

# Debugging

<purpose>
Diagnose and fix issues in the cldc compiler pipeline. Covers common failure patterns, diagnostic techniques, and recovery steps.
</purpose>

<context>
The pipeline has 3 stages where failures occur:
1. Ingest (source_loader.py) — file discovery and reading
2. Parse (rule_parser.py) — YAML validation and rule merging
3. Compile (policy_compiler.py) — lockfile generation

Errors propagate as Python exceptions with descriptive messages.
</context>

<procedure>
1. Read the full error traceback — identify which pipeline stage failed
2. Check the error message — cldc errors include source file paths and context
3. Identify the failing input:
   — Ingest errors: check CLAUDE.md exists, .claude-compiler.yaml is valid YAML
   — Parse errors: check rule YAML has required fields (id, kind), valid values
   — Compile errors: check all sources are accessible, no permission issues
4. Reproduce with minimal input — use tmp_path in a test
5. Fix the root cause, not the symptom
6. Add a regression test
7. Run full `pytest` to verify no cascading breakage
</procedure>

<patterns>
<do>
  — Use pytest -v --tb=long for detailed tracebacks
  — Use pytest -k "test_name" to isolate a single failing test
  — Add breakpoint() in code for interactive debugging
  — Check source precedence when rules seem missing — loader sorts deterministically
  — Verify YAML syntax with `python -c "import yaml; yaml.safe_load(open('file.yml'))"`
</do>
<dont>
  — Don't catch and silence exceptions during debugging
  — Don't modify test fixtures to make tests pass — fix the code
  — Don't assume the error message is wrong — verify the input first
</dont>
</patterns>

<troubleshooting>

| Symptom                                  | Cause                          | Fix                                         |
|------------------------------------------|--------------------------------|---------------------------------------------|
| ValueError: Unknown rule kind            | Typo or new kind not added     | Check ALLOWED_KINDS in rule_parser.py       |
| ValueError: Duplicate rule id            | Same ID in multiple sources    | Use globally unique rule IDs                |
| FileNotFoundError                        | Repo path doesn't exist        | Verify path passed to compile()             |
| yaml.YAMLError                           | Malformed YAML                 | Validate YAML syntax separately             |
| KeyError on rule dict                    | Missing required field         | Ensure rules have `id` and `kind`           |
| Lockfile differs between runs            | Non-deterministic ordering     | Check that all collections are sorted       |
| Tests pass locally but concept fails     | Different Python version        | Verify Python >=3.11                        |

</troubleshooting>

<references>
— src/cldc/parser/rule_parser.py: ALLOWED_KINDS, ALLOWED_MODES — validation constants
— src/cldc/ingest/source_loader.py: discover_sources() — file discovery logic
— tests/test_validation.py: examples of expected error behaviors
</references>
