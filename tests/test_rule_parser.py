from pathlib import Path

import pytest

from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents


def test_parse_rule_documents_merges_rules_from_all_sources():
    repo = Path(__file__).parent / 'fixtures' / 'repo_a'

    bundle = load_policy_sources(repo)
    parsed = parse_rule_documents(bundle)

    assert parsed.default_mode == 'warn'
    assert [rule.rule_id for rule in parsed.rules] == [
        'generated-lock',
        'must-read-rfc',
        'run-tests',
    ]
    assert parsed.rules[0].kind == 'deny_write'
    assert parsed.rules[1].before_paths == ['docs/rfcs/**']
    assert parsed.rules[2].commands == ['pytest -q']


def test_parse_rule_documents_rejects_duplicate_rule_ids(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: dup\n    kind: deny_write\n    paths: ['a/**']\n    message: first\n```\n"
    )
    (tmp_path / '.claude-compiler.yaml').write_text(
        "rules:\n  - id: dup\n    kind: deny_write\n    paths: ['b/**']\n    message: second\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match='duplicate rule id'):
        parse_rule_documents(bundle)


def test_parse_rule_documents_rejects_missing_kind_specific_fields(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\nrules:\n  - id: read-rfc\n    kind: require_read\n    paths: ['src/**']\n    message: read first\n```\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="requires field 'before_paths'"):
        parse_rule_documents(bundle)
