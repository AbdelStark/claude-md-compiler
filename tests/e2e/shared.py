"""Shared langchain e2e helpers for tests and the narrated demo runner."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

LANGCHAIN_URL = "https://github.com/langchain-ai/langchain.git"
CLONE_TIMEOUT_SECONDS = 300
POLICY_SOURCE = Path(__file__).parent / "compiler.yaml"


class LangchainE2EError(RuntimeError):
    """Raised when the upstream langchain demo/test workspace cannot be prepared."""


def shallow_clone(target: Path) -> None:
    """Shallow-clone langchain with blob filtering into `target`."""

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
        timeout=CLONE_TIMEOUT_SECONDS,
    )


def validate_langchain_layout(clone_root: Path) -> None:
    """Assert the upstream repo still has the structure the e2e flow depends on."""

    if not (clone_root / "CLAUDE.md").is_file():
        raise LangchainE2EError("upstream langchain no longer ships CLAUDE.md at the repo root")
    if not (clone_root / "libs" / "core" / "langchain_core").is_dir():
        raise LangchainE2EError("upstream langchain no longer has libs/core/langchain_core")


def clone_langchain_repo(target: Path) -> Path:
    """Clone langchain into `target` and validate the layout the e2e flow uses."""

    if shutil.which("git") is None:
        raise LangchainE2EError("git binary not on PATH; the e2e demo requires git")

    try:
        shallow_clone(target)
    except subprocess.TimeoutExpired as exc:
        raise LangchainE2EError(f"git clone timed out after {CLONE_TIMEOUT_SECONDS}s; check network or upstream") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        raise LangchainE2EError(f"git clone failed: {stderr}") from exc
    except FileNotFoundError as exc:
        raise LangchainE2EError("git binary disappeared between discovery and clone") from exc

    validate_langchain_layout(target)
    return target


def install_policy_translation(repo_root: Path) -> Path:
    """Write the hand-authored policy translation into the upstream repo clone."""

    target = repo_root / ".claude-compiler.yaml"
    target.write_text(POLICY_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def copy_langchain_worktree(source: Path, target: Path) -> Path:
    """Copy a shared langchain clone into a writable per-test worktree."""

    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git"),
    )
    install_policy_translation(target)
    return target
