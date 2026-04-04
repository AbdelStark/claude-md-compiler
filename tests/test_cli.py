import json
from pathlib import Path
import subprocess
import sys


def test_cli_compile_command(tmp_path):
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target = tmp_path / 'repo'
    target.mkdir()
    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((target / '.claude' / 'policy.lock.json').read_text())
    assert payload['rule_count'] == 3
    assert 'compiled 3 rules from 4 sources' in result.stdout.lower()


def test_cli_doctor_command_reports_repo_health(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )

    result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'doctor', str(tmp_path), '--json'],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['discovered'] is True
    assert payload['rule_count'] == 1
    assert any('compiled lockfile not found' in warning for warning in payload['warnings'])


def test_cli_check_command_returns_json_violations(tmp_path):
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target = tmp_path / 'repo'
    target.mkdir()
    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )
    assert compile_result.returncode == 0, compile_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', 'src/main.py',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is True
    assert payload['decision'] == 'warn'
    assert payload['violation_count'] == 2
    assert [violation['rule_id'] for violation in payload['violations']] == ['must-read-rfc', 'run-tests']


def test_cli_check_command_blocks_on_blocking_violations(tmp_path):
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target = tmp_path / 'repo'
    target.mkdir()
    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )
    assert compile_result.returncode == 0, compile_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', 'generated/output.json',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is False
    assert payload['decision'] == 'block'
    assert payload['blocking_violation_count'] == 1
    assert payload['violations'][0]['rule_id'] == 'generated-lock'
