"""End-to-end cldc test against langchain-ai/langchain.

The story this test tells, step by step:

1. Clone langchain at `master` (shallow, blob-less).
2. Drop a hand-authored `.claude-compiler.yaml` next to langchain's
   existing `CLAUDE.md`. The yaml translates langchain CLAUDE.md's prose
   expectations — "tests must follow source", "read the manifest before
   editing", "AI disclosure required in PRs", "run unit tests" — into
   executable cldc rules, and layers them on top of the bundled `default`
   preset (which blocks writes to generated/ and dist/).
3. Run `cldc compile` and confirm the lockfile is produced with both the
   preset rules and our custom rules.
4. Run a series of **red** checks — crafted evidence sets that should
   trigger specific rules — and assert that exactly those rules fire.
5. Run a **green** check — a full evidence set (read + couple + command +
   claim) — and assert the decision is `pass` with zero violations.
6. Feed one of the red reports into `build_fix_plan` and assert the
   remediation steps are actionable and reference the right rules.

Every test is marked `@pytest.mark.e2e` and is excluded from the default
pytest run. Invoke with `make e2e` or `uv run pytest -m e2e`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.remediation import build_fix_plan

pytestmark = pytest.mark.e2e


# ---- 1. compile phase --------------------------------------------------


def test_langchain_compile_produces_lockfile_with_preset_and_custom_rules(
    langchain_with_policy: Path,
) -> None:
    """Step 1: the compile step must succeed against a real langchain worktree.

    We assert structural invariants, not exact counts, because the bundled
    presets could grow a rule without breaking this contract.
    """

    import json

    compiled = compile_repo_policy(langchain_with_policy)

    lockfile = langchain_with_policy / ".claude" / "policy.lock.json"
    assert lockfile.is_file(), "compile should have written .claude/policy.lock.json"
    assert compiled.rule_count >= 5, f"expected at least 4 custom rules + 2 default preset rules, got {compiled.rule_count}"

    payload = json.loads(lockfile.read_text(encoding="utf-8"))
    lockfile_rule_ids = {rule["id"] for rule in payload["rules"]}

    # Our custom rules must be present.
    assert "langchain-tests-follow-core-source" in lockfile_rule_ids
    assert "langchain-read-manifest-before-core-edit" in lockfile_rule_ids
    assert "langchain-require-ai-disclosure" in lockfile_rule_ids
    assert "langchain-run-unit-tests-before-finish" in lockfile_rule_ids

    # Default preset's deny_write must also be merged in.
    assert "preset-default-generated-read-only" in lockfile_rule_ids

    # SOURCE_PRECEDENCE in the lockfile should advertise the preset kind,
    # confirming the `extends:` block was honored.
    assert "preset" in payload["source_precedence"]


# ---- 2. red phase: triggered violations --------------------------------


def test_red_editing_core_source_with_no_companion_test_blocks(
    langchain_with_policy: Path,
) -> None:
    """RED: write a core source file without a matching tests/ file.

    `langchain-tests-follow-core-source` is a block-mode couple_change
    rule. Because we also do not assert the AI-disclosure claim, a second
    rule fires in the same run — that is expected, and a useful property
    of the cldc evaluator: every violated rule surfaces in a single pass.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        write_paths=["libs/core/langchain_core/agents.py"],
    )

    assert report.decision == "block", (
        f"expected block decision, got {report.decision} with violations {[v.rule_id for v in report.violations]}"
    )
    fired = {violation.rule_id for violation in report.violations}
    assert "langchain-tests-follow-core-source" in fired
    assert "langchain-require-ai-disclosure" in fired
    assert report.blocking_violation_count >= 2


def test_red_writing_dist_output_is_blocked_by_default_preset(
    langchain_with_policy: Path,
) -> None:
    """RED: writes under `dist/**` must be blocked by the `default` preset.

    This demonstrates the preset-augmentation story: we did not author a
    generated-files rule ourselves, but we extended `default` and inherited
    it. A policy author adding our `.claude-compiler.yaml` to langchain
    gets the generated-files guard for free.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        write_paths=["libs/core/dist/langchain_core-0.0.0.tar.gz"],
    )

    assert report.decision == "block"
    assert any(v.rule_id == "preset-default-generated-read-only" for v in report.violations)
    assert report.blocking_violation_count >= 1


def test_red_missing_read_and_missing_command_surface_as_warnings(
    langchain_with_policy: Path,
) -> None:
    """RED (warn-only): edit core + include companion test + claim, but skip
    the manifest read and the unit-test command.

    Both warn-mode rules fire (`langchain-read-manifest-before-core-edit`
    and `langchain-run-unit-tests-before-finish`), producing a `warn`
    decision — not a block — which is the correct mode for advisory
    rules. Exit code from the CLI should still be 0.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        write_paths=[
            "libs/core/langchain_core/agents.py",
            "libs/core/tests/unit_tests/test_agents.py",
        ],
        claims=["ai-agent-disclosed"],
    )

    assert report.decision == "warn", f"expected warn, got {report.decision} with {[v.rule_id for v in report.violations]}"
    assert report.blocking_violation_count == 0
    fired = {violation.rule_id for violation in report.violations}
    assert "langchain-read-manifest-before-core-edit" in fired
    assert "langchain-run-unit-tests-before-finish" in fired


def test_red_claim_enforcement_requires_ai_agent_disclosed(
    langchain_with_policy: Path,
) -> None:
    """RED: wrong claim is supplied — the rule must still fire because
    claim matching is exact-string membership, not substring.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        write_paths=[
            "libs/core/langchain_core/agents.py",
            "libs/core/tests/unit_tests/test_agents.py",
        ],
        read_paths=["libs/core/pyproject.toml"],
        commands=["make test"],
        claims=["human-reviewed"],  # NOT `ai-agent-disclosed`
    )

    assert report.decision == "block"
    fired = {violation.rule_id for violation in report.violations}
    assert fired == {"langchain-require-ai-disclosure"}, f"only the AI-disclosure rule should fire, got {fired}"
    violation = report.violations[0]
    assert violation.required_claims == ["ai-agent-disclosed"]
    assert violation.matched_claims == []


# ---- 3. green phase: passing ------------------------------------------


def test_green_full_evidence_set_passes(langchain_with_policy: Path) -> None:
    """GREEN: assert the decision is `pass` when every rule is satisfied.

    Reads the manifest, writes source + companion test, runs unit tests,
    and asserts the AI-disclosure claim. This is the canonical "good
    citizen" change and the test guards against future regressions that
    would make policy satisfaction harder than intended.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        read_paths=["libs/core/pyproject.toml"],
        write_paths=[
            "libs/core/langchain_core/agents.py",
            "libs/core/tests/unit_tests/test_agents.py",
        ],
        commands=["make test"],
        claims=["ai-agent-disclosed"],
    )

    assert report.decision == "pass", (
        f"expected pass, got {report.decision} with violations {[(v.rule_id, v.message) for v in report.violations]}"
    )
    assert report.violation_count == 0
    assert report.violations == []
    assert report.summary == "Policy check passed with no violations."


def test_green_read_init_py_satisfies_require_read(langchain_with_policy: Path) -> None:
    """GREEN: the require_read rule offers two ways to satisfy it —
    reading the manifest OR the package's __init__.py. Confirm both paths.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        read_paths=["libs/core/langchain_core/__init__.py"],
        write_paths=[
            "libs/core/langchain_core/agents.py",
            "libs/core/tests/unit_tests/test_agents.py",
        ],
        commands=["uv run pytest"],
        claims=["ai-agent-disclosed"],
    )

    assert report.decision == "pass"
    assert report.violation_count == 0


# ---- 4. remediation phase ---------------------------------------------


def test_fix_plan_for_missing_test_remediation_is_actionable(
    langchain_with_policy: Path,
) -> None:
    """Build a fix plan from the red #1 report and verify its remediation
    entries include something actionable — the rule id, the message, and
    the fact that tests must be updated.
    """

    compile_repo_policy(langchain_with_policy)
    report = check_repo_policy(
        langchain_with_policy,
        write_paths=["libs/core/langchain_core/agents.py"],
    )
    assert report.decision == "block"

    plan = build_fix_plan(report.to_dict())

    assert plan["remediation_count"] >= 2
    assert plan["decision"] == "block"

    rule_ids = {remediation["rule_id"] for remediation in plan["remediations"]}
    assert "langchain-tests-follow-core-source" in rule_ids
    assert "langchain-require-ai-disclosure" in rule_ids

    tests_remediation = next(r for r in plan["remediations"] if r["rule_id"] == "langchain-tests-follow-core-source")
    assert tests_remediation["priority"] == "blocking"
    assert tests_remediation["kind"] == "couple_change"
    # At least one step must mention the word "test" (actionable guidance).
    assert any("test" in step.lower() for step in tests_remediation["steps"]), (
        f"expected at least one step to mention tests, got {tests_remediation['steps']}"
    )

    claim_remediation = next(r for r in plan["remediations"] if r["rule_id"] == "langchain-require-ai-disclosure")
    assert claim_remediation["suggested_claims"] == ["ai-agent-disclosed"]


# ---- 5. doctor integration --------------------------------------------


def test_doctor_reports_langchain_repo_as_healthy_after_compile(
    langchain_with_policy: Path,
) -> None:
    """After compile, `cldc doctor` should report the repo as healthy
    (no errors) and record the rule count we compiled.
    """

    from cldc.compiler.policy_compiler import doctor_repo_policy

    compile_repo_policy(langchain_with_policy)
    doctor = doctor_repo_policy(langchain_with_policy)

    assert doctor.discovered is True
    assert doctor.lockfile_exists is True
    assert doctor.errors == []
    assert doctor.rule_count >= 5
    # Default mode comes from our `.claude-compiler.yaml`.
    assert doctor.default_mode == "warn"
