---
name: rfc-implementation
description: Guide for implementing features from CLDC RFC specifications. Activate when working on any Phase 2/3 feature, when referencing CLDC-* numbers, or when building new compiler pipeline stages.
prerequisites: Read the target RFC fully before starting implementation.
---

# RFC Implementation

<purpose>
Translate frozen RFC specifications into working code. Each RFC defines a contract with acceptance criteria, schema, and test requirements. This skill ensures implementations match specs precisely.
</purpose>

<context>
RFCs live in docs/rfcs/CLDC-NNNN-*.md. They are numbered sequentially and grouped by phase:
- Phase 1 (DONE): 0001-0003 — source model, rule DSL, lockfile
- Phase 2 (NEXT): 0004-0007 — repo scanner, events, validator, enforcement
- Phase 3 (LATER): 0008-0012 — autofix, CLI, CI, reports, presets

Each RFC contains: motivation, detailed design, schema definitions, acceptance criteria, and failure modes.
</context>

<procedure>
1. Read the target RFC completely: docs/rfcs/CLDC-NNNN-*.md
2. Identify which src/cldc/ subdirectory the feature belongs to:
   — New pipeline stage? Create new subdirectory under src/cldc/
   — Extension of existing stage? Add to existing module
   — Cross-cutting? May need changes in multiple modules
3. Check RFC dependencies — some RFCs build on others (e.g., 0006 needs 0005)
4. Design the data model first — define classes/dataclasses matching RFC schemas
5. Implement core logic — follow the pipeline pattern (input → transform → output)
6. Write tests matching RFC acceptance criteria — each criterion = at least one test
7. Add test fixtures if needed in tests/fixtures/
8. Run `pytest` — all tests must pass
9. Verify backward compatibility — existing lockfile format must not break
</procedure>

<patterns>
<do>
  — Map RFC schema fields directly to Python class attributes
  — Use the existing SourceBundle/ParsedPolicy/CompiledPolicy chain as integration points
  — Add new entry points to the CLI in src/cldc/cli/main.py following existing argparse pattern
  — Include provenance in all new data structures (source file, line number)
</do>
<dont>
  — Don't deviate from RFC schemas without explicit approval
  — Don't add dependencies — solve with stdlib + PyYAML
  — Don't modify existing lockfile format_version without bumping it
  — Don't implement partial RFCs — each RFC is an atomic unit of work
</dont>
</patterns>

<examples>
Example: Implementing a new pipeline stage (like CLDC-0006 Validator)

```python
# src/cldc/validator/__init__.py
# src/cldc/validator/engine.py

from dataclasses import dataclass
from cldc.compiler.policy_compiler import CompiledPolicy

@dataclass
class ValidationResult:
    rule_id: str
    status: str  # "pass" | "violation" | "skipped"
    message: str
    source_path: str

def validate(policy: CompiledPolicy, events: list) -> list[ValidationResult]:
    """Evaluate events against compiled policy rules."""
    results = []
    # ... implementation matching CLDC-0006 spec
    return results
```
</examples>

<troubleshooting>

| Symptom                        | Cause                         | Fix                                |
|--------------------------------|-------------------------------|------------------------------------|
| RFC references unknown schema  | Depends on unimplemented RFC  | Implement dependency RFC first     |
| Tests pass but output differs  | Non-deterministic ordering    | Sort all collections before output |
| Lockfile breaks existing tests | Schema change without version | Bump format_version               |

</troubleshooting>

<references>
— docs/rfcs/README.md: RFC index with phase groupings
— docs/specs/product-spec.md: Overall product vision and principles
— src/cldc/compiler/policy_compiler.py: Current pipeline endpoint — new stages integrate here
— tests/fixtures/repo_a/: Reference fixture for testing
</references>
