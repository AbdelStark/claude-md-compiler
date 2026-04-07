from pathlib import Path

import pytest

from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents


def test_parse_rule_documents_merges_rules_from_all_sources():
    repo = Path(__file__).parent / "fixtures" / "repo_a"

    bundle = load_policy_sources(repo)
    parsed = parse_rule_documents(bundle)

    assert parsed.default_mode == "warn"
    assert [rule.rule_id for rule in parsed.rules] == [
        "generated-lock",
        "must-read-rfc",
        "run-tests",
    ]
    assert parsed.rules[0].kind == "deny_write"
    assert parsed.rules[1].before_paths == ["docs/rfcs/**"]
    assert parsed.rules[2].commands == ["pytest -q"]


def test_parse_rule_documents_rejects_duplicate_rule_ids(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: dup\n    kind: deny_write\n    paths: ['a/**']\n    message: first\n```\n"
    )
    (tmp_path / ".claude-compiler.yaml").write_text("rules:\n  - id: dup\n    kind: deny_write\n    paths: ['b/**']\n    message: second\n")

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="duplicate rule id"):
        parse_rule_documents(bundle)


def test_parse_rule_documents_rejects_missing_kind_specific_fields(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: read-rfc\n    kind: require_read\n    paths: ['src/**']\n    message: read first\n```\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="requires field 'before_paths'"):
        parse_rule_documents(bundle)


def test_parse_rule_documents_accepts_require_claim_rule(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: qa-sign-off\n"
        "    kind: require_claim\n"
        "    mode: block\n"
        "    when_paths: ['src/**']\n"
        "    claims: ['qa-reviewed', 'security-reviewed']\n"
        "    message: QA must sign off before editing source.\n"
        "```\n"
    )

    bundle = load_policy_sources(tmp_path)
    parsed = parse_rule_documents(bundle)

    assert len(parsed.rules) == 1
    rule = parsed.rules[0]
    assert rule.rule_id == "qa-sign-off"
    assert rule.kind == "require_claim"
    assert rule.mode == "block"
    assert rule.when_paths == ["src/**"]
    assert rule.claims == ["qa-reviewed", "security-reviewed"]

    serialized = rule.to_dict()
    assert serialized["kind"] == "require_claim"
    assert serialized["claims"] == ["qa-reviewed", "security-reviewed"]
    assert serialized["when_paths"] == ["src/**"]


def test_parse_rule_documents_rejects_require_claim_without_claims(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: missing-claims\n    kind: require_claim\n    when_paths: ['src/**']\n    message: needs claim\n```\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="requires field 'claims'"):
        parse_rule_documents(bundle)


def test_parse_rule_documents_rejects_require_claim_without_when_paths(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "```cldc\nrules:\n  - id: missing-when-paths\n    kind: require_claim\n    claims: ['qa-reviewed']\n    message: needs scope\n```\n"
    )

    bundle = load_policy_sources(tmp_path)

    with pytest.raises(ValueError, match="requires field 'when_paths'"):
        parse_rule_documents(bundle)
