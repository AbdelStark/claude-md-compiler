import json
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy


@pytest.fixture
def compiled_repo(tmp_path):
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target = tmp_path / 'repo'
    target.mkdir()

    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    compile_repo_policy(target)
    return target


def test_check_repo_policy_reports_warn_only_violations(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=['src/main.py'],
    )

    assert report.ok is True
    assert report.decision == 'warn'
    assert report.violation_count == 2
    assert report.blocking_violation_count == 0
    assert [violation.rule_id for violation in report.violations] == ['must-read-rfc', 'run-tests']
    require_read = report.violations[0]
    assert require_read.required_paths == ['docs/rfcs/**']
    require_command = report.violations[1]
    assert require_command.required_commands == ['pytest -q']


def test_check_repo_policy_passes_when_required_inputs_are_present(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        read_paths=['docs/rfcs/CLDC-0006-validator-engine.md'],
        write_paths=['src/main.py'],
        commands=['pytest -q'],
    )

    assert report.ok is True
    assert report.decision == 'pass'
    assert report.violations == []


def test_check_repo_policy_blocks_deny_write_rule(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=['generated/output.json'],
    )

    assert report.ok is False
    assert report.decision == 'block'
    assert report.blocking_violation_count == 1
    violation = report.violations[0]
    assert violation.rule_id == 'generated-lock'
    assert violation.mode == 'block'
    assert violation.matched_paths == ['generated/output.json']


def test_check_repo_policy_requires_existing_lockfile(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# repo\n')

    with pytest.raises(FileNotFoundError, match='cldc compile'):
        check_repo_policy(tmp_path)


def test_check_repo_policy_rejects_malformed_lockfile(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# repo\n')
    lock_dir = tmp_path / '.claude'
    lock_dir.mkdir()
    (lock_dir / 'policy.lock.json').write_text('{not-json')

    with pytest.raises(ValueError, match='not valid JSON'):
        check_repo_policy(tmp_path)
