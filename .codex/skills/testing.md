---
name: testing
description: Testing patterns and conventions for cldc. Activate when writing tests, adding fixtures, debugging test failures, or validating new features against RFC acceptance criteria.
prerequisites: pytest installed via `pip install -e ".[dev]"`
---

# Testing

<purpose>
Write effective tests for the cldc compiler pipeline. Covers unit tests, integration tests, fixture management, and mapping RFC criteria to test cases.
</purpose>

<context>
Test framework: pytest >=8.0
Test location: tests/ (configured in pyproject.toml)
Python path: src/ (configured in pyproject.toml)
Current test count: 11 across 5 files
Fixture repo: tests/fixtures/repo_a/ (CLAUDE.md + config + policy file with 3 rules)
</context>

<procedure>
1. Determine test type:
   — Unit test: isolated function behavior → test_<module>.py
   — Validation test: error handling → test_validation.py
   — CLI test: end-to-end via subprocess → test_cli.py
   — Integration: full pipeline → test_compiler.py
2. Create test function with descriptive name: test_<what>_<condition>
3. Arrange: set up inputs (use fixtures or tmp_path for temp repos)
4. Act: call the function under test
5. Assert: verify outputs match RFC spec exactly
6. Run `pytest -v` to confirm
</procedure>

<patterns>
<do>
  — Use pytest's tmp_path fixture for tests that create files
  — Test both success and failure paths
  — Test determinism: call twice, assert identical output
  — Use subprocess.run for CLI tests (see test_cli.py pattern)
  — Assert specific error messages, not just exception types
  — Create minimal fixtures — only the files needed for the test case
</do>
<dont>
  — Don't modify tests/fixtures/repo_a/ for new tests — create new fixtures or use tmp_path
  — Don't use unittest.mock unless testing external I/O — prefer real fixtures
  — Don't write tests that depend on execution order
  — Don't assert on timestamps or absolute paths in lockfile output
</dont>
</patterns>

<examples>
Example: Testing a new rule kind validation

```python
# tests/test_validation.py

def test_invalid_rule_kind_raises():
    rules_yaml = [{"id": "r1", "kind": "nonexistent_kind"}]
    with pytest.raises(ValueError, match="Unknown rule kind"):
        parse_rules(rules_yaml)

def test_new_kind_happy_path(tmp_path):
    policy_file = tmp_path / "policies" / "test.yml"
    policy_file.parent.mkdir()
    policy_file.write_text("rules:\n  - id: r1\n    kind: new_kind\n    paths: ['*.py']\n")
    # ... load and assert
```
</examples>

<troubleshooting>

| Symptom                    | Cause                     | Fix                              |
|----------------------------|---------------------------|----------------------------------|
| ImportError in tests       | Package not installed      | `pip install -e ".[dev]"`        |
| Fixture not found          | Wrong relative path        | Use Path(__file__).parent for base |
| Test pollution             | Shared mutable state       | Use tmp_path, don't modify fixtures |

</troubleshooting>

<references>
— tests/test_cli.py: CLI subprocess testing pattern
— tests/test_compiler.py: Integration test showing full pipeline
— tests/test_validation.py: Error handling test patterns
— tests/fixtures/repo_a/: Reference fixture structure
</references>
