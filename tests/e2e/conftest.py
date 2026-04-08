"""Shared fixtures for the end-to-end policy tests.

The session-scoped `langchain_repo` fixture shallow-clones langchain-ai/langchain
into a pytest-managed tmpdir exactly once per pytest session. Tests that
need a fresh worktree each time use `langchain_with_policy`, which copies
the session clone into a per-test tmpdir and drops
`tests/e2e/compiler.yaml` in as `.claude-compiler.yaml`.

Both fixtures are defensive: they skip (not fail) the current test if the
network is down, git is missing, or the upstream clone raises. That keeps
`uv run pytest -m e2e` from turning into a flake machine when the network
has a bad day.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .shared import LangchainE2EError, clone_langchain_repo, copy_langchain_worktree


@pytest.fixture(scope="session")
def langchain_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Shallow clone of langchain master, shared across the e2e session."""

    target = tmp_path_factory.mktemp("cldc-e2e-langchain")
    clone_root = target / "langchain"
    try:
        clone_langchain_repo(clone_root)
    except LangchainE2EError as exc:
        pytest.skip(str(exc))

    return clone_root


@pytest.fixture
def langchain_with_policy(langchain_repo: Path, tmp_path: Path) -> Path:
    """Per-test copy of the session clone with our .claude-compiler.yaml added.

    The session clone is read-only from each test's perspective; tests that
    need to mutate the worktree (e.g. to run `cldc compile` which writes
    `.claude/policy.lock.json`) get a fresh `tmp_path` copy.
    """

    return copy_langchain_worktree(langchain_repo, tmp_path / "langchain")
