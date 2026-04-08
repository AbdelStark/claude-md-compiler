"""Git integration for `cldc ci`.

`collect_git_write_paths` runs `git diff` against either the staging area or
a base/head range and returns the changed paths plus deterministic provenance
metadata that can be embedded in a check report. Subprocess failures, invalid
flag combinations, and a missing `git` binary on PATH are all surfaced as
`GitError` so callers can route on the typed exception.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cldc.errors import GitError
from cldc.ingest.discovery import discover_policy_repo


def _run_git(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git` with stdout and stderr captured, raising `GitError` on failure."""

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # The `git` executable itself is not on PATH. Surface a targeted,
        # actionable error instead of a generic FileNotFoundError.
        raise GitError("`git` executable not found on PATH; install git to use `cldc ci`") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise GitError(f"git command failed ({' '.join(command)}): {stderr}")
    return result


def collect_git_write_paths(
    repo_root: Path | str,
    *,
    staged: bool = False,
    base: str | None = None,
    head: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Collect changed paths from git and return them with provenance metadata.

    Args:
        repo_root: Any path inside the target repo; the function walks up to
            find the policy root via `discover_policy_repo`.
        staged: Use `git diff --cached --name-only` (mutually exclusive with
            `base`/`head`).
        base: Base ref for a range diff. Required when `staged` is False.
        head: Head ref for a range diff. Defaults to `HEAD` when `base` is
            set and `head` is not.

    Returns:
        A tuple `(write_paths, metadata)` where `write_paths` is a list of
        repo-relative POSIX paths and `metadata` is a dict containing the
        mode, base/head refs (when applicable), the exact git command that
        was run, and the number of changed paths.

    Raises:
        GitError: Invalid flag combination, git command failure, or git
            binary not on PATH.
        FileNotFoundError: `repo_root` does not contain any cldc policy
            markers (delegated from `discover_policy_repo`).
    """

    discovery = discover_policy_repo(repo_root)
    if not discovery.discovered:
        raise FileNotFoundError(discovery.warnings[0])

    if staged and base:
        raise GitError("cldc ci accepts either --staged or --base/--head, not both")
    if head and not base:
        # Check the head/base pair before the broader "something must be set"
        # check so the error message points at the actual mistake.
        raise GitError("cldc ci cannot use --head without --base")
    if not staged and not base:
        raise GitError("cldc ci requires either --staged or --base")

    root = Path(discovery.repo_root)
    _run_git(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)

    if staged:
        command = ["git", "diff", "--cached", "--name-only"]
        metadata: dict[str, Any] = {
            "mode": "staged",
            "git_command": command,
        }
    else:
        resolved_head = head or "HEAD"
        command = ["git", "diff", "--name-only", f"{base}...{resolved_head}"]
        metadata = {
            "mode": "range",
            "base": base,
            "head": resolved_head,
            "git_command": command,
        }

    result = _run_git(command, cwd=root)
    write_paths = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    metadata["write_path_count"] = len(write_paths)
    return write_paths, metadata
