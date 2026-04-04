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
    assert payload['$schema'] == 'https://cldc.dev/schemas/policy-lock/v1'
    assert payload['compiler_version'] == '0.1.0'
    assert payload['default_mode'] == 'warn'
    assert payload['source_precedence'] == [
        'claude_md',
        'inline_block',
        'compiler_config',
        'policy_file',
    ]
    assert [rule['id'] for rule in payload['rules']] == [
        'generated-lock',
        'must-read-rfc',
        'run-tests',
    ]
    assert compiled.lockfile_path == '.claude/policy.lock.json'
    assert compiled.source_count == 4


def test_compile_repo_policy_discovers_repo_root_from_nested_path(tmp_path):
    repo = tmp_path / 'repo'
    nested = repo / 'src' / 'pkg'
    nested.mkdir(parents=True)
    (repo / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )

    compiled = compile_repo_policy(nested)

    assert compiled.repo_root == str(repo.resolve())
    assert (repo / '.claude' / 'policy.lock.json').exists()
