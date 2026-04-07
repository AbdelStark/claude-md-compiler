from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONFIG_CANDIDATES = (".claude-compiler.yaml", ".claude-compiler.yml")
DEFAULT_POLICY_GLOBS = ("policies/*.yml", "policies/*.yaml")
LOCKFILE_PATH = ".claude/policy.lock.json"


@dataclass(frozen=True)
class DiscoveryResult:
    """Discovery metadata for the nearest policy-bearing repository."""

    start_path: str
    repo_root: str
    discovered: bool
    claude_path: str | None
    config_path: str | None
    config_candidates: list[str]
    policy_paths: list[str]
    lockfile_path: str | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of every field."""
        return asdict(self)


def _list_default_policy_paths(root: Path) -> list[str]:
    policy_paths: set[str] = set()
    for pattern in DEFAULT_POLICY_GLOBS:
        for policy_path in root.glob(pattern):
            if policy_path.is_file():
                policy_paths.add(policy_path.relative_to(root).as_posix())
    return sorted(policy_paths)


def discover_policy_repo(start_path: Path | str) -> DiscoveryResult:
    """Walk up from a path until a repository with policy markers is found.

    A "policy marker" is a `CLAUDE.md`, a `.claude-compiler.yaml`/`.yml`, or
    a `policies/*.yml` file. Discovery starts at `start_path` and walks up
    the directory tree until a marker is found or the filesystem root is
    reached; the returned `DiscoveryResult` records which markers were
    present and which are missing so callers can emit actionable warnings.

    Raises:
        FileNotFoundError: `start_path` does not exist on disk. The error
            message includes the resolved path plus a hint about passing an
            existing directory, so the CLI shell can surface it as-is.
    """

    original = Path(start_path)
    if not original.exists():
        raise FileNotFoundError(
            f"Repo path not found: {original} — pass an existing directory inside a repo with a CLAUDE.md, "
            f".claude-compiler.yaml, or policies/*.yml"
        )

    cursor = original.resolve()
    if cursor.is_file():
        cursor = cursor.parent

    for candidate in [cursor, *cursor.parents]:
        claude_file = candidate / "CLAUDE.md"
        config_candidates = [name for name in CONFIG_CANDIDATES if (candidate / name).is_file()]
        policy_paths = _list_default_policy_paths(candidate)
        lockfile_file = candidate / LOCKFILE_PATH
        has_markers = claude_file.is_file() or bool(config_candidates) or bool(policy_paths)
        if not has_markers:
            continue

        warnings: list[str] = []
        if len(config_candidates) > 1:
            warnings.append("multiple compiler config files found; using .claude-compiler.yaml precedence")
        if not claude_file.is_file():
            warnings.append("CLAUDE.md not found; compiling config and policy fragments only")
        if not policy_paths:
            warnings.append("no policy fragments discovered under policies/*.yml or policies/*.yaml")
        if not lockfile_file.is_file():
            warnings.append("compiled lockfile not found at .claude/policy.lock.json")

        preferred_config = config_candidates[0] if config_candidates else None
        return DiscoveryResult(
            start_path=str(original.resolve()),
            repo_root=str(candidate),
            discovered=True,
            claude_path="CLAUDE.md" if claude_file.is_file() else None,
            config_path=preferred_config,
            config_candidates=config_candidates,
            policy_paths=policy_paths,
            lockfile_path=LOCKFILE_PATH if lockfile_file.is_file() else None,
            warnings=warnings,
        )

    return DiscoveryResult(
        start_path=str(original.resolve()),
        repo_root=str(cursor),
        discovered=False,
        claude_path=None,
        config_path=None,
        config_candidates=[],
        policy_paths=[],
        lockfile_path=None,
        warnings=["no CLAUDE.md, compiler config, or policy fragments found while searching parent directories"],
    )
