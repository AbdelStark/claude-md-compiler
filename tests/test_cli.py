import json
import subprocess
import sys
from pathlib import Path

from cldc.runtime.remediation import FIX_PLAN_FORMAT_VERSION, FIX_PLAN_SCHEMA
from cldc.runtime.report_schema import CHECK_REPORT_FORMAT_VERSION, CHECK_REPORT_SCHEMA

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


def test_cli_check_command_human_output_includes_summary_and_next_action(tmp_path):
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
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert 'Policy check: warn' in result.stdout
    assert 'Summary: Policy check found 2 non-blocking violation(s).' in result.stdout
    assert 'Recommended next action: Read at least one path matching docs/rfcs/** before modifying src/main.py.' in result.stdout
    assert "why: Write activity src/main.py triggered require_read rule 'must-read-rfc', but no required read matched docs/rfcs/**." in result.stdout


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
    assert payload['$schema'] == CHECK_REPORT_SCHEMA
    assert payload['format_version'] == CHECK_REPORT_FORMAT_VERSION
    assert payload['ok'] is True
    assert payload['decision'] == 'warn'
    assert payload['summary'] == 'Policy check found 2 non-blocking violation(s).'
    assert payload['next_action'] == 'Read at least one path matching docs/rfcs/** before modifying src/main.py.'
    assert payload['violation_count'] == 2
    assert payload['violations'][0]['explanation'] == "Write activity src/main.py triggered require_read rule 'must-read-rfc', but no required read matched docs/rfcs/**."
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
    assert payload['summary'] == 'Policy check passed with no violations.'
    assert payload['next_action'] is None
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
    assert payload['summary'] == 'Policy check found 1 violation(s), including 1 blocking violation(s).'
    assert payload['next_action'] == 'Avoid writing paths matching generated/**.'
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
    assert payload['summary'] == 'Policy check found 1 violation(s), including 1 blocking violation(s).'
    assert payload['next_action'] == 'Avoid writing paths matching generated/**.'
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



def test_cli_explain_command_renders_text_from_fresh_inputs(tmp_path):
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
            '-m', 'cldc.cli.main', 'explain', str(target),
            '--write', 'src/main.py',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert 'Policy explanation: warn' in result.stdout
    assert 'Rule provenance:' in result.stdout
    assert 'must-read-rfc' in result.stdout
    assert 'run-tests' in result.stdout



def test_cli_explain_command_renders_markdown_from_saved_report(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    report_path = tmp_path / 'report.json'

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    check_result = subprocess.run(
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
    assert check_result.returncode == 2, check_result.stderr
    report_path.write_text(check_result.stdout)

    explain_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'explain', str(target),
            '--report-file', str(report_path),
            '--format', 'markdown',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert explain_result.returncode == 0, explain_result.stderr
    assert '# Policy Explanation' in explain_result.stdout
    assert '## Violations' in explain_result.stdout
    assert 'generated-lock' in explain_result.stdout
    assert 'Rule provenance' in explain_result.stdout


def test_cli_explain_command_accepts_legacy_unversioned_saved_report(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    report_path = tmp_path / 'legacy-report.json'

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    check_result = subprocess.run(
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
    assert check_result.returncode == 2, check_result.stderr
    legacy_payload = json.loads(check_result.stdout)
    legacy_payload.pop('$schema')
    legacy_payload.pop('format_version')
    report_path.write_text(json.dumps(legacy_payload))

    explain_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'explain', str(target),
            '--report-file', str(report_path),
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert explain_result.returncode == 0, explain_result.stderr
    payload = json.loads(explain_result.stdout)
    assert payload['$schema'] == CHECK_REPORT_SCHEMA
    assert payload['format_version'] == CHECK_REPORT_FORMAT_VERSION
    assert payload['decision'] == 'block'
    assert payload['violations'][0]['rule_id'] == 'generated-lock'


def test_cli_fix_command_returns_versioned_json_plan(tmp_path):
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

    fix_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'fix', str(target),
            '--write', 'src/main.py',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert fix_result.returncode == 0, fix_result.stderr
    payload = json.loads(fix_result.stdout)
    assert payload['$schema'] == FIX_PLAN_SCHEMA
    assert payload['format_version'] == FIX_PLAN_FORMAT_VERSION
    assert payload['decision'] == 'warn'
    assert payload['remediation_count'] == 2
    assert payload['next_action'] == (
        'Read at least one required context path before keeping changes to src/main.py: docs/rfcs/**.'
    )
    assert payload['remediations'][1]['suggested_commands'] == ['pytest -q']


def test_cli_fix_command_renders_markdown_from_saved_report(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    report_path = tmp_path / 'report.json'

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    check_result = subprocess.run(
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
    assert check_result.returncode == 2, check_result.stderr
    report_path.write_text(check_result.stdout)

    fix_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'fix', str(target),
            '--report-file', str(report_path),
            '--format', 'markdown',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert fix_result.returncode == 0, fix_result.stderr
    assert '# Policy Fix Plan' in fix_result.stdout
    assert '## Remediations' in fix_result.stdout
    assert 'generated-lock' in fix_result.stdout
    assert 'Suggested commands' not in fix_result.stdout



def test_cli_fix_command_rejects_mixed_saved_report_and_runtime_inputs(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    report_path = tmp_path / 'report.json'

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    check_result = subprocess.run(
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
    assert check_result.returncode == 2, check_result.stderr
    report_path.write_text(check_result.stdout)

    fix_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'fix', str(target),
            '--report-file', str(report_path),
            '--write', 'src/main.py',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert fix_result.returncode == 1
    payload = json.loads(fix_result.stderr)
    assert payload['ok'] is False
    assert 'cannot combine saved report input with fresh runtime evidence' in payload['error']



def test_cli_check_command_writes_json_report_to_output_file(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    output_path = tmp_path / 'artifacts' / 'policy-report.json'

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
            '--output', str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 2, result.stderr
    assert output_path.exists()
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert stdout_payload['decision'] == 'block'
    assert stdout_payload['violations'][0]['rule_id'] == 'generated-lock'



def test_cli_explain_and_fix_support_saved_artifact_export(tmp_path):
    target = tmp_path / 'repo'
    _copy_fixture_repo(target)
    report_path = tmp_path / 'artifacts' / 'policy-report.json'
    explain_path = tmp_path / 'artifacts' / 'explain.md'
    fix_path = tmp_path / 'artifacts' / 'fix-plan.json'

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    check_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', 'generated/output.json',
            '--json',
            '--output', str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert check_result.returncode == 2, check_result.stderr
    assert report_path.exists()

    explain_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'explain', str(target),
            '--report-file', str(report_path),
            '--format', 'markdown',
            '--output', str(explain_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert explain_result.returncode == 0, explain_result.stderr
    assert explain_path.exists()
    assert explain_path.read_text() == explain_result.stdout
    assert '# Policy Explanation' in explain_result.stdout

    fix_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'fix', str(target),
            '--report-file', str(report_path),
            '--json',
            '--output', str(fix_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert fix_result.returncode == 0, fix_result.stderr
    assert fix_path.exists()
    stdout_payload = json.loads(fix_result.stdout)
    file_payload = json.loads(fix_path.read_text())
    assert stdout_payload == file_payload
    assert stdout_payload['$schema'] == FIX_PLAN_SCHEMA
    assert stdout_payload['remediation_count'] == 1



def test_cli_check_command_enforces_require_claim_rule(tmp_path):
    target = tmp_path / 'repo'
    target.mkdir()
    (target / 'CLAUDE.md').write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
    )

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    missing_claim_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', 'src/app.py',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert missing_claim_result.returncode == 2, missing_claim_result.stderr
    payload = json.loads(missing_claim_result.stdout)
    assert payload['decision'] == 'block'
    assert payload['blocking_violation_count'] == 1
    assert payload['violations'][0]['rule_id'] == 'qa-sign-off'
    assert payload['violations'][0]['kind'] == 'require_claim'
    assert payload['violations'][0]['required_claims'] == ['qa-reviewed']
    assert payload['violations'][0]['matched_claims'] == []

    passing_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'check', str(target),
            '--write', 'src/app.py',
            '--claim', 'qa-reviewed',
            '--json',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert passing_result.returncode == 0, passing_result.stderr
    passing_payload = json.loads(passing_result.stdout)
    assert passing_payload['decision'] == 'pass'
    assert passing_payload['inputs']['claims'] == ['qa-reviewed']


def test_cli_check_text_output_surfaces_required_claims(tmp_path):
    target = tmp_path / 'repo'
    target.mkdir()
    (target / 'CLAUDE.md').write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: warn\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
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
            '--write', 'src/app.py',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert 'Policy check: warn' in result.stdout
    assert 'qa-sign-off (require_claim)' in result.stdout
    assert 'required claims: qa-reviewed' in result.stdout
    assert 'next step: Record one of the required claims before finishing: qa-reviewed.' in result.stdout


def test_cli_check_command_accepts_events_file_with_claim_rule(tmp_path):
    target = tmp_path / 'repo'
    target.mkdir()
    (target / 'CLAUDE.md').write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
    )
    events_path = tmp_path / 'events.json'
    events_path.write_text(
        json.dumps(
            {
                'events': [
                    {'kind': 'write', 'path': 'src/app.py'},
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


def test_cli_fix_command_renders_require_claim_remediation(tmp_path):
    target = tmp_path / 'repo'
    target.mkdir()
    (target / 'CLAUDE.md').write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
    )

    compile_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    fix_result = subprocess.run(
        [
            sys.executable,
            '-m', 'cldc.cli.main', 'fix', str(target),
            '--write', 'src/app.py',
            '--format', 'markdown',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert fix_result.returncode == 0, fix_result.stderr
    assert '# Policy Fix Plan' in fix_result.stdout
    assert 'qa-sign-off' in fix_result.stdout
    assert '**Suggested claims:** `qa-reviewed`' in fix_result.stdout


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
    assert '--output' in result.stdout
    assert '--claim' in result.stdout
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
    assert '--output' in ci_help.stdout

    explain_help = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'explain', '--help'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert explain_help.returncode == 0
    assert '--report-file' in explain_help.stdout
    assert '--stdin-report' in explain_help.stdout
    assert '--format' in explain_help.stdout
    assert '--output' in explain_help.stdout

    fix_help = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'fix', '--help'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert fix_help.returncode == 0
    assert '--report-file' in fix_help.stdout
    assert '--stdin-report' in fix_help.stdout
    assert '--format' in fix_help.stdout
    assert '--events-file' in fix_help.stdout
    assert '--output' in fix_help.stdout

    version_result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', '--version'],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert version_result.returncode == 0
    assert version_result.stdout.strip().startswith('cldc 0.1.0')
