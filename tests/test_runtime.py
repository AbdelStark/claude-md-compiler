import json
import os
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.events import load_execution_inputs


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
    assert report.inputs['claims'] == []


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


def test_load_execution_inputs_supports_batch_events_and_claims():
    payload = {
        'events': [
            {'kind': 'read', 'path': 'docs/rfcs/CLDC-0006-validator-engine.md'},
            {'kind': 'write', 'path': 'src/main.py'},
            {'kind': 'command', 'command': 'pytest -q'},
            {'kind': 'claim', 'claim': 'task-complete'},
        ]
    }

    inputs = load_execution_inputs(payload)

    assert inputs.read_paths == ['docs/rfcs/CLDC-0006-validator-engine.md']
    assert inputs.write_paths == ['src/main.py']
    assert inputs.commands == ['pytest -q']
    assert inputs.claims == ['task-complete']


def test_load_execution_inputs_rejects_malformed_event_payloads():
    with pytest.raises(ValueError, match='must be a JSON object'):
        load_execution_inputs(['bad'])

    with pytest.raises(ValueError, match="events\\[0\\] must contain a string 'kind'"):
        load_execution_inputs({'events': [{}]})

    with pytest.raises(ValueError, match="events\\[0\\] kind 'write' requires a string 'path'"):
        load_execution_inputs({'events': [{'kind': 'write'}]})


def test_check_repo_policy_normalizes_absolute_paths_inside_repo(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        write_paths=[str((compiled_repo / 'src/main.py').resolve())],
    )

    assert report.decision == 'warn'
    assert [violation.rule_id for violation in report.violations] == ['must-read-rfc', 'run-tests']
    assert report.inputs['write_paths'] == ['src/main.py']


def test_check_repo_policy_merges_explicit_inputs_with_event_payload(compiled_repo):
    report = check_repo_policy(
        compiled_repo,
        read_paths=['docs/rfcs/CLDC-0006-validator-engine.md'],
        event_payload={
            'events': [
                {'kind': 'write', 'path': 'src/main.py'},
                {'kind': 'command', 'command': 'pytest -q'},
                {'kind': 'claim', 'claim': 'completed-runtime-check'},
            ]
        },
    )

    assert report.ok is True
    assert report.decision == 'pass'
    assert report.inputs['claims'] == ['completed-runtime-check']


def test_check_repo_policy_rejects_paths_outside_repo(compiled_repo, tmp_path):
    outside = tmp_path / 'elsewhere.txt'
    outside.write_text('nope\n')

    with pytest.raises(ValueError, match='outside the discovered repo root'):
        check_repo_policy(compiled_repo, write_paths=[str(outside.resolve())])


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


def test_check_repo_policy_rejects_lockfile_schema_drift(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile = tmp_path / '.claude' / 'policy.lock.json'
    payload = json.loads(lockfile.read_text())
    payload['$schema'] = 'https://cldc.dev/schemas/policy-lock/v0'
    lockfile.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match='schema does not match'):
        check_repo_policy(tmp_path, write_paths=['generated/output.json'])


def test_check_repo_policy_rejects_stale_lockfile(tmp_path):
    claude_path = tmp_path / 'CLAUDE.md'
    claude_path.write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )
    compile_repo_policy(tmp_path)
    lockfile_mtime = (tmp_path / '.claude' / 'policy.lock.json').stat().st_mtime
    claude_path.write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: changed\n```\n"
    )
    os.utime(claude_path, (lockfile_mtime + 5, lockfile_mtime + 5))

    with pytest.raises(ValueError, match='appears stale'):
        check_repo_policy(tmp_path, write_paths=['generated/output.json'])
