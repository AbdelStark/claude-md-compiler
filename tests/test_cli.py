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
