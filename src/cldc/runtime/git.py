from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cldc.ingest.discovery import discover_policy_repo


def _run_git(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise ValueError(f"git command failed ({' '.join(command)}): {stderr}")
    return result


def collect_git_write_paths(
    repo_root: Path | str,
    *,
    staged: bool = False,
    base: str | None = None,
    head: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Collect changed paths from git and return them with provenance metadata."""

    discovery = discover_policy_repo(repo_root)
    if not discovery.discovered:
        raise FileNotFoundError(discovery.warnings[0])

    root = Path(discovery.repo_root)
    _run_git(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)

    if staged and base:
        raise ValueError("cldc ci accepts either --staged or --base/--head, not both")
    if not staged and not base:
        raise ValueError("cldc ci requires either --staged or --base")
    if head and not base:
        raise ValueError("cldc ci cannot use --head without --base")

    if staged:
        command = ["git", "diff", "--cached", "--name-only"]
        mode = "staged"
        metadata: dict[str, Any] = {
            "mode": mode,
            "git_command": command,
        }
    else:
        resolved_head = head or "HEAD"
        command = ["git", "diff", "--name-only", f"{base}...{resolved_head}"]
        mode = "range"
        metadata = {
            "mode": mode,
            "base": base,
            "head": resolved_head,
            "git_command": command,
        }

    result = _run_git(command, cwd=root)
    write_paths = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    metadata["write_path_count"] = len(write_paths)
    return write_paths, metadata
