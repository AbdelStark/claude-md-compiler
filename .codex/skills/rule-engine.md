---
name: rule-engine
description: Guide for extending the rule engine with new rule kinds, validation logic, and enforcement behavior. Activate when adding rule types, modifying validation, or working on CLDC-0002/0006/0007 features.
prerequisites: Understand existing rule kinds in src/cldc/parser/rule_parser.py
---

# Rule Engine

<purpose>
Extend the cldc rule system with new rule kinds, validation constraints, and enforcement behaviors. The rule engine is the core of the policy system.
</purpose>

<context>
Current rule kinds (defined in rule_parser.py ALLOWED_KINDS):
  — require_read: force reading files before touching others
  — deny_write: forbid modifications to paths
  — require_command: require running commands when paths touched
  — couple_change: enforce coupled file changes

Current enforcement modes (ALLOWED_MODES):
  — observe: detect only
  — warn: emit violation, allow action
  — block: prevent action
  — fix: auto-remediate

Rule fields: id (required), kind (required), message, mode, paths, before_paths, when_paths, commands, source_path, source_block_id

RuleDefinition dataclass: src/cldc/parser/rule_parser.py
</context>

<procedure>
Adding a new rule kind:
1. Add kind string to ALLOWED_KINDS set in rule_parser.py
2. Define which fields are required/optional for this kind
3. Add validation in the rule parsing logic (check required fields per kind)
4. Add test for valid rule of new kind in test_rule_parser.py
5. Add test for invalid rule (missing required fields) in test_validation.py
6. Update test fixture if the new kind needs demonstration
7. Run `pytest`

Adding kind-specific validation:
1. In rule_parser.py, add a validation function: validate_<kind>(rule_dict)
2. Call it from the main parse path when kind matches
3. Raise ValueError with descriptive message on invalid input
4. Test both valid and invalid cases
</procedure>

<patterns>
<do>
  — Keep ALLOWED_KINDS and ALLOWED_MODES as the single source of truth
  — Validate kind-specific required fields (e.g., couple_change needs paths + when_paths)
  — Include the rule ID in all error messages for traceability
  — Preserve provenance (source_path, source_block_id) through all transformations
</do>
<dont>
  — Don't add kinds not defined in an RFC without approval
  — Don't make fields universally required if only some kinds need them
  — Don't change existing rule serialization format without bumping format_version
</dont>
</patterns>

<examples>
Example: Adding kind-specific field validation

```python
# In rule_parser.py

def _validate_rule_fields(rule: dict, source_path: str) -> None:
    kind = rule["kind"]
    rule_id = rule["id"]
    
    if kind == "couple_change" and not rule.get("when_paths"):
        raise ValueError(
            f"Rule '{rule_id}' of kind 'couple_change' requires 'when_paths' "
            f"(source: {source_path})"
        )
    
    if kind == "require_command" and not rule.get("commands"):
        raise ValueError(
            f"Rule '{rule_id}' of kind 'require_command' requires 'commands' "
            f"(source: {source_path})"
        )
```
</examples>

<references>
— src/cldc/parser/rule_parser.py: Core rule parsing and validation
— docs/rfcs/CLDC-0002-rule-dsl-v1.md: Rule DSL specification
— docs/rfcs/CLDC-0006-validator-engine.md: How rules get evaluated
— docs/rfcs/CLDC-0007-enforcement-modes.md: Mode behavior definitions
— tests/test_rule_parser.py: Rule parsing tests
— tests/test_validation.py: Validation error tests
</references>
