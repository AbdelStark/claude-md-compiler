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



def _init_git_repo(target: Path) -> None:
    commands = [
        ['git', 'init'],
        ['git', 'config', 'user.email', 'cldc-tests@example.com'],
        ['git', 'config', 'user.name', 'CLDC Tests'],
        ['git', 'add', '.'],
        ['git', 'commit', '-m', 'baseline'],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=target,
        )
        assert result.returncode == 0, result.stderr


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
    assert isinstance(payload['source_digest'], str)
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


def test_cli_check_command_accepts_events_file_json(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    events_path = tmp_path / 'events.json'
    events_path.write_text(
        json.dumps(
            {
                'events': [
                    {'kind': 'read', 'path': 'docs/rfcs/CLDC-0006-validator-engine.md'},
                    {'kind': 'write', 'path': 'src/main.py'},
                    {'kind': 'command', 'command': 'pytest -q'},
                    {'kind': 'claim', 'claim': 'qa-reviewed'},
                ]
            }
        )
    )

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
            '--events-file', str(events_path),
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['decision'] == 'pass'
    assert payload['inputs']['claims'] == ['qa-reviewed']


def test_cli_check_command_accepts_stdin_json(tmp_path):
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
            '--stdin-json',
            '--json',
        ],
        input=json.dumps({'write_paths': ['generated/output.json']}),
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload['decision'] == 'block'
    assert payload['violations'][0]['rule_id'] == 'generated-lock'


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


def test_cli_check_command_reports_json_errors_for_bad_event_payload(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    bad_events = tmp_path / 'bad-events.json'
    bad_events.write_text(json.dumps({'events': [{'kind': 'write'}]}))

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
            '--events-file', str(bad_events),
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload['command'] == 'check'
    assert 'requires a string' in payload['error']



def test_cli_ci_command_uses_staged_git_diff(tmp_path):
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
    _init_git_repo(target)

    (target / 'src').mkdir(exist_ok=True)
    (target / 'src' / 'main.py').write_text('print("changed")\n')
    stage_result = subprocess.run(
        ['git', 'add', 'src/main.py'],
        capture_output=True,
        text=True,
        check=False,
        cwd=target,
    )
    assert stage_result.returncode == 0, stage_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'ci', str(target),
            '--staged',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['decision'] == 'warn'
    assert payload['inputs']['write_paths'] == ['src/main.py']
    assert payload['git']['mode'] == 'staged'



def test_cli_ci_command_uses_base_head_diff(tmp_path):
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
    _init_git_repo(target)

    base_result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        capture_output=True,
        text=True,
        check=False,
        cwd=target,
    )
    assert base_result.returncode == 0, base_result.stderr
    base_sha = base_result.stdout.strip()

    generated = target / 'generated' / 'output.json'
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text('{"status": "changed"}\n')
    add_result = subprocess.run(
        ['git', 'add', 'generated/output.json'],
        capture_output=True,
        text=True,
        check=False,
        cwd=target,
    )
    assert add_result.returncode == 0, add_result.stderr
    commit_result = subprocess.run(
        ['git', 'commit', '-m', 'touch generated output'],
        capture_output=True,
        text=True,
        check=False,
        cwd=target,
    )
    assert commit_result.returncode == 0, commit_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'ci', str(target),
            '--base', base_sha,
            '--head', 'HEAD',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload['decision'] == 'block'
    assert payload['inputs']['write_paths'] == ['generated/output.json']
    assert payload['git']['mode'] == 'range'
    assert payload['git']['base'] == base_sha
    assert payload['git']['head'] == 'HEAD'



def test_cli_ci_command_reports_json_errors_for_missing_git_selector(tmp_path):
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
    _init_git_repo(target)

    result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'ci', str(target),
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload['command'] == 'ci'
    assert 'requires either --staged or --base' in payload['error']



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
    assert '--events-file' in result.stdout
    assert '--stdin-json' in result.stdout
    assert 'discovered' in result.stdout

    ci_help = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'ci', '--help'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert ci_help.returncode == 0
    assert '--staged' in ci_help.stdout
    assert '--base' in ci_help.stdout
    assert '--head' in ci_help.stdout

    version_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', '--version'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert version_result.returncode == 0
    assert version_result.stdout.strip().startswith('cldc 0.1.0')
