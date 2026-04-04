from pathlib import Path

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
        "```cldc\nrules:\n  - id: dup\n    kind: deny_write\n    paths: ['a/**']\n```\n"
    )
    (tmp_path / '.claude-compiler.yaml').write_text(
        "rules:\n  - id: dup\n    kind: deny_write\n    paths: ['b/**']\n"
    )

    bundle = load_policy_sources(tmp_path)

    try:
        parse_rule_documents(bundle)
    except ValueError as exc:
        assert 'duplicate rule id' in str(exc).lower()
    else:
        raise AssertionError('expected duplicate rule id to raise')
