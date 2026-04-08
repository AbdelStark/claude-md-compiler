from __future__ import annotations

import subprocess
from importlib.metadata import version

import cldc


def _run(*args: str) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def main() -> int:
    installed_version = version("claude-md-compiler")

    assert cldc.__version__ == installed_version
    assert _run("cldc", "--version") == f"cldc {installed_version}"

    help_text = _run("cldc", "--help")
    for command in ("init", "compile", "doctor", "check", "ci", "explain", "fix", "preset", "tui", "hook"):
        assert command in help_text, f"command {command!r} missing from `cldc --help`"

    # Confirm bundled presets ship inside the wheel and are addressable.
    preset_list = _run("cldc", "preset", "list")
    for preset_name in ("default", "strict", "docs-sync"):
        assert preset_name in preset_list, f"bundled preset {preset_name!r} missing from `cldc preset list`"

    # Confirm hook generation works without filesystem side effects.
    git_hook = _run("cldc", "hook", "generate", "git-pre-commit")
    assert "cldc ci" in git_hook, "git pre-commit hook should invoke `cldc ci`"
    claude_hook = _run("cldc", "hook", "generate", "claude-code")
    assert "SessionStart" in claude_hook, "claude-code hook snippet should declare a SessionStart hook"
    assert "PostToolUse" in claude_hook, "claude-code hook snippet should declare a PostToolUse hook"
    assert "PostToolUseFailure" in claude_hook, "claude-code hook snippet should declare a PostToolUseFailure hook"
    assert "Stop" in claude_hook, "claude-code hook snippet should declare a Stop hook"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
