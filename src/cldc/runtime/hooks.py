"""Hook script generation and installation for `cldc`.

`cldc hook` bridges the gap between the evidence-driven enforcement model
of `cldc check`/`cldc ci` and the actual moments at which a developer or
agent finishes work. It emits two complementary hook artifacts:

* a portable POSIX `git pre-commit` script that runs `cldc ci --staged`
  before every commit and blocks the commit on policy violations, and
* a `.claude/settings.json` snippet that wires `cldc` into Claude Code's
  hook lifecycle with a session-state adapter: `PreToolUse` blocks true
  preconditions before writes, `PostToolUse` records evidence and reports
  workflow drift, `PostToolUseFailure` records failed commands, and `Stop`
  blocks completion while blocking invariants remain unmet.

Generators are pure functions that return string content; the installer
functions are the only entry points that touch the filesystem, and they
refuse to clobber existing scripts unless `force=True` is passed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cldc._logging import get_logger
from cldc.errors import CldcError

logger = get_logger(__name__)

GIT_PRE_COMMIT_HOOK_PATH = ".git/hooks/pre-commit"
CLAUDE_SETTINGS_PATH = ".claude/settings.json"

SUPPORTED_HOOK_KINDS = ("git-pre-commit", "claude-code")
INSTALLABLE_HOOK_KINDS = ("git-pre-commit",)


class HookError(CldcError):
    """Raised when a hook cannot be generated or installed."""


@dataclass(frozen=True)
class HookArtifact:
    """A generated hook script plus enough context to render it.

    `target_path` is the repo-relative POSIX path the artifact would be
    written to by `cldc hook install`. For non-installable artifacts
    (e.g. the Claude Code settings snippet) it is the conventional path
    a user would copy the content into.
    """

    kind: str
    target_path: str
    executable: bool
    content: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict with stable key ordering."""
        payload = asdict(self)
        return {key: payload[key] for key in ("kind", "target_path", "executable", "content")}


@dataclass(frozen=True)
class HookInstallReport:
    """Deterministic outcome of `cldc hook install`."""

    kind: str
    repo_root: str
    target_path: str
    action: str  # "created", "updated", or "skipped"
    executable: bool
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict with stable key ordering."""
        payload = asdict(self)
        return {key: payload[key] for key in ("kind", "repo_root", "target_path", "action", "executable", "next_action")}


_GIT_PRE_COMMIT_TEMPLATE = """\
#!/bin/sh
# Managed by `cldc hook install git-pre-commit`.
#
# Runs `cldc ci --staged` before every commit so that staged write paths
# are evaluated against the compiled policy lockfile. Exits non-zero on
# blocking violations, which aborts the commit.
#
# To bypass this hook for an individual commit, run `git commit --no-verify`.
# To remove it, delete this file or run `cldc hook install git-pre-commit
# --force` to regenerate it.

set -eu

if ! command -v cldc >/dev/null 2>&1; then
    echo "cldc pre-commit hook: 'cldc' is not on PATH; skipping policy check" >&2
    echo "  install cldc or remove .git/hooks/pre-commit to silence this notice" >&2
    exit 0
fi

repo_root=$(git rev-parse --show-toplevel)
exec cldc ci "$repo_root" --staged
"""


_CLAUDE_SETTINGS_HOOK_TEMPLATE = {
    "hooks": {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-session-start "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-pre-tool-use "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Read|Edit|Write|MultiEdit|Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-post-tool-use "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
        "PostToolUseFailure": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-post-tool-use-failure "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-stop "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
        "SessionEnd": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": ('cldc hook runtime claude-session-end "$CLAUDE_PROJECT_DIR"'),
                    }
                ],
            }
        ],
    }
}


def generate_git_pre_commit() -> HookArtifact:
    """Return the git pre-commit hook script artifact."""
    return HookArtifact(
        kind="git-pre-commit",
        target_path=GIT_PRE_COMMIT_HOOK_PATH,
        executable=True,
        content=_GIT_PRE_COMMIT_TEMPLATE,
    )


def generate_claude_code_settings() -> HookArtifact:
    """Return a `.claude/settings.json` snippet that wires the Claude adapter.

    The content is a self-contained JSON document; users can copy it
    verbatim into a fresh `.claude/settings.json`, or merge the `hooks`
    block into an existing settings file by hand.
    """
    content = json.dumps(_CLAUDE_SETTINGS_HOOK_TEMPLATE, indent=2, sort_keys=True) + "\n"
    return HookArtifact(
        kind="claude-code",
        target_path=CLAUDE_SETTINGS_PATH,
        executable=False,
        content=content,
    )


def generate_hook(kind: str) -> HookArtifact:
    """Dispatch to the generator for `kind` and return its artifact."""
    if kind == "git-pre-commit":
        return generate_git_pre_commit()
    if kind == "claude-code":
        return generate_claude_code_settings()
    joined = ", ".join(SUPPORTED_HOOK_KINDS)
    raise HookError(f"unknown hook kind: {kind!r}; supported kinds: {joined}")


def _resolve_repo_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).expanduser().resolve()
    if not root.exists():
        raise HookError(f"repo path does not exist: {root}")
    if not root.is_dir():
        raise HookError(f"repo path is not a directory: {root}")
    return root


def install_git_pre_commit(repo_root: Path | str, *, force: bool = False) -> HookInstallReport:
    """Install the git pre-commit hook into `.git/hooks/pre-commit`.

    Refuses to overwrite a pre-existing hook script unless `force=True`.
    Requires the target directory to contain a `.git` directory; this
    sidesteps the surprise of writing into a worktree or submodule whose
    hooks live elsewhere.
    """
    root = _resolve_repo_root(repo_root)
    git_dir = root / ".git"
    if not git_dir.is_dir():
        raise HookError(f"no .git directory found at {git_dir}; run `git init` before installing the pre-commit hook")

    artifact = generate_git_pre_commit()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = git_dir / "hooks" / "pre-commit"

    action: str
    if target.exists():
        if not force:
            raise HookError(f"{GIT_PRE_COMMIT_HOOK_PATH} already exists; pass force=True (or `--force` from the CLI) to overwrite it")
        target.write_text(artifact.content, encoding="utf-8")
        action = "updated"
    else:
        target.write_text(artifact.content, encoding="utf-8")
        action = "created"

    target.chmod(0o755)
    logger.debug("%s git pre-commit hook at %s", action, target)

    return HookInstallReport(
        kind="git-pre-commit",
        repo_root=str(root),
        target_path=GIT_PRE_COMMIT_HOOK_PATH,
        action=action,
        executable=True,
        next_action=(
            "Stage a change and run `git commit` to verify the hook fires; use `git commit --no-verify` to bypass it for a single commit."
        ),
    )


def install_hook(kind: str, repo_root: Path | str, *, force: bool = False) -> HookInstallReport:
    """Install hook `kind` into `repo_root`. Only installable kinds are accepted."""
    if kind == "git-pre-commit":
        return install_git_pre_commit(repo_root, force=force)
    if kind in SUPPORTED_HOOK_KINDS:
        raise HookError(f"hook kind {kind!r} is generate-only; copy `cldc hook generate {kind}` output into {CLAUDE_SETTINGS_PATH} by hand")
    joined = ", ".join(INSTALLABLE_HOOK_KINDS)
    raise HookError(f"unknown installable hook kind: {kind!r}; supported kinds: {joined}")
