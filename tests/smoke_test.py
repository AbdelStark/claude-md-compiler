from __future__ import annotations

from importlib.metadata import version
import subprocess

import cldc


def _run(*args: str) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def main() -> int:
    installed_version = version("claude-md-compiler")

    assert cldc.__version__ == installed_version
    assert _run("cldc", "--version") == f"cldc {installed_version}"

    help_text = _run("cldc", "--help")
    for command in ("compile", "doctor", "check", "ci", "explain", "fix"):
        assert command in help_text

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
