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

import shutil
import subprocess
from pathlib import Path

import pytest

LANGCHAIN_URL = "https://github.com/langchain-ai/langchain.git"
_CLONE_TIMEOUT_SECONDS = 300
_POLICY_SOURCE = Path(__file__).parent / "compiler.yaml"


def _shallow_clone(target: Path) -> None:
    """Shallow-clone langchain with blob filter + single branch into `target`."""

    cmd = [
        "git",
        "clone",
        "--depth=1",
        "--filter=blob:none",
        "--single-branch",
        "--quiet",
        LANGCHAIN_URL,
        str(target),
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=_CLONE_TIMEOUT_SECONDS,
    )


@pytest.fixture(scope="session")
def langchain_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Shallow clone of langchain master, shared across the e2e session."""

    if shutil.which("git") is None:
        pytest.skip("git binary not on PATH — e2e tests require git")

    target = tmp_path_factory.mktemp("cldc-e2e-langchain")
    clone_root = target / "langchain"
    try:
        _shallow_clone(clone_root)
    except subprocess.TimeoutExpired:
        pytest.skip(f"git clone timed out after {_CLONE_TIMEOUT_SECONDS}s — check network or upstream")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        pytest.skip(f"git clone failed: {stderr}")
    except FileNotFoundError:
        pytest.skip("git binary disappeared between which() and clone — skipping")

    # Sanity check: if langchain restructures the repo, the test cannot
    # meaningfully enforce its CLAUDE.md and should skip cleanly.
    if not (clone_root / "CLAUDE.md").is_file():
        pytest.skip("upstream langchain no longer ships CLAUDE.md at the repo root")
    if not (clone_root / "libs" / "core" / "langchain_core").is_dir():
        pytest.skip("upstream langchain no longer has libs/core/langchain_core")

    return clone_root


@pytest.fixture
def langchain_with_policy(langchain_repo: Path, tmp_path: Path) -> Path:
    """Per-test copy of the session clone with our .claude-compiler.yaml added.

    The session clone is read-only from each test's perspective; tests that
    need to mutate the worktree (e.g. to run `cldc compile` which writes
    `.claude/policy.lock.json`) get a fresh `tmp_path` copy.
    """

    target = tmp_path / "langchain"
    shutil.copytree(
        langchain_repo,
        target,
        # Exclude the .git directory to keep the copy small and fast.
        ignore=shutil.ignore_patterns(".git"),
    )

    # Drop our policy translation in as `.claude-compiler.yaml` at the
    # repo root. cldc discovery will find it alongside CLAUDE.md.
    (target / ".claude-compiler.yaml").write_text(
        _POLICY_SOURCE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    return target
