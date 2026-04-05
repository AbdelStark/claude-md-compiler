import json
from pathlib import Path
import subprocess
import sys


PYTHONPATH_ENV = {'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}


def _copy_fixture_repo(target: Path) -> None:
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target.mkdir()
    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())


def test_cli_compile_command(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)

    result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
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
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['discovered'] is True
    assert payload['rule_count'] == 1
    assert any('compiled lockfile not found' in warning for warning in payload['warnings'])


def test_cli_check_command_returns_json_violations(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
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
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is True
    assert payload['decision'] == 'warn'
    assert payload['violation_count'] == 2
    assert [violation['rule_id'] for violation in payload['violations']] == ['must-read-rfc', 'run-tests']


def test_cli_check_command_accepts_absolute_paths(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', str((target / 'src/main.py').resolve()),
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['inputs']['write_paths'] == ['src/main.py']
    assert [violation['rule_id'] for violation in payload['violations']] == ['must-read-rfc', 'run-tests']


def test_cli_check_command_blocks_on_blocking_violations(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
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
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is False
    assert payload['decision'] == 'block'
    assert payload['blocking_violation_count'] == 1
    assert payload['violations'][0]['rule_id'] == 'generated-lock'


def test_cli_help_exposes_version_and_absolute_path_support():
    result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'check', '--help'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0
    assert 'repo-relative or absolute' in result.stdout
    assert 'discovered' in result.stdout

    version_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', '--version'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert version_result.returncode == 0
    assert version_result.stdout.strip().startswith('cldc 0.1.0')
