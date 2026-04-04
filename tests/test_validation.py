from pathlib import Path
import subprocess
import sys

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents


def test_loader_discovers_policy_files_without_include_config(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# ok\n')
    policies = tmp_path / 'policies'
    policies.mkdir()
    (policies / 'base.yml').write_text(
        "rules:\n  - id: implicit\n    kind: deny_write\n    paths: ['generated/**']\n    message: implicit\n"
    )

    bundle = load_policy_sources(tmp_path)

    assert [source.kind for source in bundle.sources] == ['claude_md', 'policy_file']
    assert bundle.sources[1].path == 'policies/base.yml'


def test_parser_rejects_invalid_default_mode(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# ok\n')
    (tmp_path / '.claude-compiler.yaml').write_text('default_mode: chaos\n')

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match='default_mode'):
        parse_rule_documents(bundle)


def test_parser_rejects_unknown_rule_kind(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: weird\n    kind: nonsense\n    message: nope\n```\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match='unknown rule kind'):
        parse_rule_documents(bundle)


def test_cli_returns_nonzero_and_actionable_error_on_bad_input(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: broken\n    message: missing kind\n```\n"
    )

    result = subprocess.run(
        [sys.executable, '-m', 'cldc.cli.main', 'compile', str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env={'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')},
    )

    assert result.returncode == 1
    assert 'compile failed' in result.stderr.lower()


def test_compiler_emits_lockfile_schema_version(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: deny\n    kind: deny_write\n    paths: ['generated/**']\n    message: stop\n```\n"
    )

    compiled = compile_repo_policy(tmp_path)

    assert compiled.format_version == '1'
