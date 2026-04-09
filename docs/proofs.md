# Formal Verification Proofs

This document outlines the formal verification proofs generated for the critical areas of the `claude-md-compiler` project using LeanStral.

## Overview

Formal verification ensures the correctness, determinism, and safety of the critical components in the project. The proofs cover:

1. **Policy Compilation** (`policy_compiler.py`)
2. **Runtime Evaluation** (`evaluator.py`)
3. **Rule Parsing** (`rule_parser.py`)
4. **Git Integration** (`git.py`)
5. **Hook Generation** (`hooks.py`)

## Proofs Directory

The proofs are located in the `proofs/` directory:

```
proofs/
├── policy_compiler.lean
├── runtime_evaluator.lean
├── rule_parser.lean
├── git_integration.lean
└── hook_generation.lean
```

## Proofs Summary

### 1. Policy Compilation (`policy_compiler.lean`)

**State Transitions:**
- `Initial` → `SourcesLoaded` → `RulesParsed` → `LockfileGenerated` → `Completed`

**Theorems:**
- `compilation_completes`: Ensures the compilation process reaches the completed state.
- `correct_transitions`: Validates each step transitions correctly.
- `deterministic_compilation`: Ensures the compilation process is deterministic.
- `accurate_lockfile`: Validates lockfile generation accuracy.
- `deterministic_digest`: Ensures source digest computation is deterministic.
- `accurate_rule_count`: Validates rule count accuracy.
- `accurate_source_count`: Validates source count accuracy.

### 2. Runtime Evaluation (`runtime_evaluator.lean`)

**State Transitions:**
- `Initial` → `EvidenceNormalized` → `RulesEvaluated` → `ViolationsDetected` → `Completed`

**Theorems:**
- `evaluation_completes`: Ensures the evaluation process reaches the completed state.
- `correct_transitions`: Validates each step transitions correctly.
- `deterministic_evaluation`: Ensures the evaluation process is deterministic.
- `safe_path_normalization`: Validates path normalization is repo-boundary-safe.
- `exhaustive_rule_evaluation`: Ensures rule evaluation is exhaustive.
- `accurate_violation_detection`: Validates violation detection accuracy.
- `correct_decision_logic`: Ensures decision logic is correct.

### 3. Rule Parsing (`rule_parser.lean`)

**State Transitions:**
- `Initial` → `SourcesLoaded` → `RulesValidated` → `RulesNormalized` → `Completed`

**Theorems:**
- `parsing_completes`: Ensures the parsing process reaches the completed state.
- `correct_transitions`: Validates each step transitions correctly.
- `deterministic_parsing`: Ensures the parsing process is deterministic.
- `validates_required_fields`: Validates all required fields are covered.
- `detects_duplicate_ids`: Ensures duplicate rule IDs are detected.
- `preserves_semantics`: Validates rule normalization preserves semantics.
- `exhaustive_validation`: Ensures rule validation is exhaustive.
- `accurate_normalization`: Validates rule normalization accuracy.

### 4. Git Integration (`git_integration.lean`)

**State Transitions:**
- `Initial` → `CommandConstructed` → `CommandExecuted` → `PathsCollected` → `Completed`

**Theorems:**
- `git_integration_completes`: Ensures the git integration process reaches the completed state.
- `correct_transitions`: Validates each step transitions correctly.
- `deterministic_git_integration`: Ensures the git integration process is deterministic.
- `correct_command_construction`: Validates git command construction correctness.
- `consistent_path_normalization`: Ensures path normalization is consistent.
- `deterministic_command_execution`: Validates git command execution is deterministic.
- `accurate_write_paths_collection`: Ensures write paths collection is accurate.

### 5. Hook Generation (`hook_generation.lean`)

**State Transitions:**
- `Initial` → `ArtifactGenerated` → `ArtifactInstalled` → `Completed`

**Theorems:**
- `hook_generation_completes`: Ensures the hook generation process reaches the completed state.
- `correct_transitions`: Validates each step transitions correctly.
- `deterministic_hook_generation`: Ensures the hook generation process is deterministic.
- `deterministic_hook_content`: Validates hook content is deterministic.
- `idempotent_installation`: Ensures installation is idempotent.
- `correct_git_pre_commit`: Validates the git pre-commit hook is correct.
- `correct_claude_code_settings`: Validates the Claude Code settings hook is correct.
- `accurate_hook_installation`: Ensures hook installation is accurate.

## Validation

To validate the proofs, you can use the Lean theorem prover to check each `.lean` file in the `proofs/` directory. Ensure you have Lean installed and configured in your environment.

### Manual Validation

Run the validation script manually:

```bash
chmod +x scripts/validate_proofs.sh
./scripts/validate_proofs.sh
```

### Automated Validation

The proofs are automatically validated in the CI/CD pipeline via the `validate_proofs` GitHub Actions workflow. This workflow runs on every push and pull request to the `main` branch.

## Integration

The proofs are integrated into the project documentation to provide formal guarantees of correctness and determinism for the critical components. They serve as a reference for understanding the expected behavior and invariants of the system.

## Future Work

- Extend proofs to cover additional edge cases and boundary conditions.
- Integrate automated proof checking into the CI/CD pipeline.
- Expand formal verification to other modules as needed.