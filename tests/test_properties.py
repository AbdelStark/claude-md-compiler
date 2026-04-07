"""Hypothesis property-based tests for cldc invariants.

These tests codify the fuzzing invariants that cldc must maintain under
adversarial input. They complement the deterministic example-based tests
in the rest of the suite.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.ingest.discovery import DiscoveryResult
from cldc.ingest.source_loader import PolicySource, SourceBundle
from cldc.parser.rule_parser import ParsedPolicy, parse_rule_documents
from cldc.runtime.evaluator import (
    _matches_any,
    _matching_claims,
    _matching_commands,
    _normalize_paths,
    check_repo_policy,
)
from cldc.runtime.events import EMPTY_EXECUTION_INPUTS, load_execution_inputs

# Safe path fragment alphabet: only letters, digits, dot, dash, underscore.
# No glob metacharacters (*, ?, [, ]) so fnmatch literal-matches paths.
_SAFE_PATH_CHARS = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="._-",
)
_safe_path_segment = st.text(alphabet=_SAFE_PATH_CHARS, min_size=1, max_size=12)
_safe_relative_path = (
    st.lists(_safe_path_segment, min_size=1, max_size=5)
    .map("/".join)
    .filter(lambda s: ".." not in s and not s.startswith("/"))
)
# Identifier-shaped tokens used for command and claim names.
_lower_token = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=8,
)
_function_fixture_settings = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
# Canonical execution-input payload shape used by both check and loader tests.
_evidence_payload = st.fixed_dictionaries(
    {
        "read_paths": st.lists(_safe_relative_path, max_size=5),
        "write_paths": st.lists(_safe_relative_path, max_size=5),
        "commands": st.lists(_lower_token, max_size=5),
        "claims": st.lists(_lower_token, max_size=5),
    }
)


@pytest.fixture(scope="session")
def simple_repo(tmp_path_factory):
    """Compile a tiny repo with a single deny_write rule for property tests."""

    repo = tmp_path_factory.mktemp("property_repo")
    (repo / "CLAUDE.md").write_text(
        "```cldc\n"
        "rules:\n"
        "  - id: deny-generated\n"
        "    kind: deny_write\n"
        "    paths: ['generated/**']\n"
        "    message: no generated writes\n"
        "```\n",
        encoding="utf-8",
    )
    compile_repo_policy(repo)
    return repo


def _make_bundle(repo_root: str, documents: list[dict[str, Any]]) -> SourceBundle:
    """Wrap a sequence of YAML-shaped dicts in a SourceBundle for parser tests."""

    sources = [
        PolicySource(
            kind="policy_file",
            path=f"policies/fuzz_{index}.yml",
            content=yaml.safe_dump(document) if document is not None else "",
        )
        for index, document in enumerate(documents)
    ]
    discovery = DiscoveryResult(
        start_path=repo_root,
        repo_root=repo_root,
        discovered=True,
        claude_path=None,
        config_path=None,
        config_candidates=[],
        policy_paths=[source.path for source in sources],
        lockfile_path=None,
        warnings=[],
    )
    return SourceBundle(repo_root=repo_root, sources=sources, discovery=discovery)


class TestNormalizePathsProperties:
    @_function_fixture_settings
    @given(paths=st.lists(_safe_relative_path, max_size=10))
    def test_normalize_returns_repo_relative_posix_or_raises(self, tmp_path, paths):
        try:
            normalized = _normalize_paths(paths, repo_root=tmp_path)
        except ValueError:
            return

        for entry in normalized:
            assert isinstance(entry, str)
            assert entry, "normalized entries are non-empty"
            assert not entry.startswith("/"), f"unexpected leading slash in {entry!r}"
            assert not entry.endswith("/"), f"unexpected trailing slash in {entry!r}"
            assert "//" not in entry, f"unexpected duplicate slash in {entry!r}"
            assert "../" not in entry and not entry.endswith("/.."), (
                f"unexpected parent traversal in {entry!r}"
            )
            assert entry != ".", "current-directory entries should be filtered"

    @_function_fixture_settings
    @given(paths=st.lists(_safe_relative_path, max_size=10))
    def test_normalize_is_idempotent(self, tmp_path, paths):
        try:
            once = _normalize_paths(paths, repo_root=tmp_path)
        except ValueError:
            return
        twice = _normalize_paths(once, repo_root=tmp_path)
        assert once == twice

    @_function_fixture_settings
    @given(path=_safe_relative_path.map(lambda s: f"../{s}"))
    def test_escapes_always_raise(self, tmp_path, path):
        with pytest.raises(ValueError, match="outside the discovered repo root"):
            _normalize_paths([path], repo_root=tmp_path)


class TestMatchesAnyProperties:
    @given(
        path=_safe_relative_path,
        extra=st.lists(_safe_path_segment, max_size=5),
    )
    def test_adding_patterns_is_monotonic(self, path, extra):
        # Without glob metacharacters, a path always literally matches itself.
        assert _matches_any(path, [path]) is True
        assert _matches_any(path, [path, *extra]) is True
        assert _matches_any(path, [*extra, path]) is True

    def test_empty_pattern_list_returns_false(self):
        assert _matches_any("foo/bar", []) is False
        assert _matches_any("foo/bar", None) is False

    @given(extra=st.lists(_safe_path_segment, min_size=1, max_size=5))
    def test_no_pattern_match_stays_false_under_disjoint_patterns(self, extra):
        # A leading-slash path can never literally equal a relative segment.
        assume(all("/" not in token for token in extra))
        assert _matches_any("/absolute/literal", extra) is False


def _is_filtered_subsequence(result: list[str], items: list[str]) -> bool:
    """Return True when ``result`` is ``items`` with some entries removed in place."""

    cursor = 0
    for entry in result:
        try:
            cursor = items.index(entry, cursor) + 1
        except ValueError:
            return False
    return True


# `_matching_claims` and `_matching_commands` share an identical implementation
# shape: filter ``items`` by membership in ``expected``. Both must be exercised
# directly so a future refactor that diverges them is caught.
_MATCHING_HELPERS = pytest.mark.parametrize(
    "matcher",
    [_matching_claims, _matching_commands],
    ids=["matching_claims", "matching_commands"],
)


class TestMatchingHelpersProperties:
    @_MATCHING_HELPERS
    @given(
        items=st.lists(_lower_token, max_size=10),
        expected=st.lists(_lower_token, max_size=10),
    )
    def test_result_is_filtered_subsequence_of_items(self, matcher, items, expected):
        result = matcher(items, expected)

        assert all(item in items for item in result)
        assert all(item in expected for item in result)
        assert _is_filtered_subsequence(result, items)

    @_MATCHING_HELPERS
    @given(items=st.lists(_lower_token, max_size=10))
    def test_empty_expected_returns_empty(self, matcher, items):
        assert matcher(items, None) == []
        assert matcher(items, []) == []


# Parser tests synthesize bundles without touching the filesystem, so a
# fabricated repo_root string is sufficient and avoids function-scoped fixtures.
_PARSER_REPO_ROOT = "/tmp/cldc-property-parser"
_yaml_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.text(max_size=20),
)
_yaml_value = st.recursive(
    _yaml_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(max_size=8), children, max_size=3),
    ),
    max_leaves=5,
)
_random_yaml_document = st.dictionaries(
    keys=st.sampled_from(["rules", "default_mode", "extra", "noise"]),
    values=_yaml_value,
    max_size=4,
)


class TestRuleParserRobustness:
    @settings(max_examples=30, deadline=None)
    @given(documents=st.lists(_random_yaml_document, max_size=3))
    def test_parse_rule_documents_either_succeeds_or_raises_value_error(self, documents):
        bundle = _make_bundle(_PARSER_REPO_ROOT, documents)
        try:
            policy = parse_rule_documents(bundle)
        except ValueError:
            return

        assert isinstance(policy, ParsedPolicy)
        for rule in policy.rules:
            assert rule.rule_id
            assert rule.kind

    def test_empty_bundle_yields_empty_policy(self):
        bundle = _make_bundle(_PARSER_REPO_ROOT, [])
        policy = parse_rule_documents(bundle)
        assert isinstance(policy, ParsedPolicy)
        assert policy.rules == []
        assert policy.default_mode == "warn"


class TestCheckRepoPolicyRobustness:
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(write_paths=st.lists(_safe_relative_path, max_size=6))
    def test_check_never_crashes_on_random_paths(self, simple_repo, write_paths):
        try:
            report = check_repo_policy(simple_repo, write_paths=write_paths)
        except ValueError:
            return

        assert report.decision in {"pass", "warn", "block"}
        assert report.violation_count >= 0
        assert report.blocking_violation_count >= 0
        assert report.blocking_violation_count <= report.violation_count

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(payload=_evidence_payload)
    def test_check_with_mixed_inputs_never_crashes(self, simple_repo, payload):
        try:
            report = check_repo_policy(simple_repo, **payload)
        except ValueError:
            return

        assert report.decision in {"pass", "warn", "block"}
        # The deny_write fixture rule never inspects reads, commands, or claims,
        # so any violations must come from the write set.
        assert all(violation.kind == "deny_write" for violation in report.violations)


class TestEvidenceLoaderProperties:
    @given(payload=_evidence_payload)
    def test_merged_with_empty_is_identity(self, payload):
        inputs = load_execution_inputs(payload)
        merged = inputs.merged_with(EMPTY_EXECUTION_INPUTS)

        assert merged.read_paths == inputs.read_paths
        assert merged.write_paths == inputs.write_paths
        assert merged.commands == inputs.commands
        assert merged.claims == inputs.claims

    @given(payload=_evidence_payload)
    def test_load_execution_inputs_preserves_field_order(self, payload):
        inputs = load_execution_inputs(payload)

        assert inputs.read_paths == payload["read_paths"]
        assert inputs.write_paths == payload["write_paths"]
        assert inputs.commands == payload["commands"]
        assert inputs.claims == payload["claims"]
