import json
from pathlib import Path

from cldc.compiler.policy_compiler import compile_repo_policy


def test_compile_repo_policy_writes_lockfile(tmp_path):
    fixture = Path(__file__).parent / 'fixtures' / 'repo_a'
    target = tmp_path / 'repo'
    target.mkdir()

    for source in fixture.rglob('*'):
        if source.is_file():
            destination = target / source.relative_to(fixture)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    compiled = compile_repo_policy(target)

    lockfile = target / '.claude' / 'policy.lock.json'
    assert lockfile.exists()
    payload = json.loads(lockfile.read_text())
    assert payload['compiler_version'] == '0.1.0'
    assert payload['default_mode'] == 'warn'
    assert [rule['id'] for rule in payload['rules']] == [
        'generated-lock',
        'must-read-rfc',
        'run-tests',
    ]
    assert compiled.lockfile_path == '.claude/policy.lock.json'
