"""Top-level public API for the `claude-md-compiler` package.

`cldc` compiles repository policy from `CLAUDE.md`, `.claude-compiler.yaml`,
`policies/*.yml`, and bundled preset packs into a versioned lockfile, then
enforces that lockfile against runtime evidence and git-derived diffs.

This module re-exports the typed exception hierarchy and the package version
so library consumers can write::

    from cldc import __version__, CldcError

without reaching into the internal module layout. Higher-level entry points
live under their dedicated subpackages (`cldc.compiler`, `cldc.runtime`,
`cldc.presets`, `cldc.scaffold`, `cldc.tui`); see `docs/library-usage.md` for
the full library reference.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from cldc.errors import (
    CldcError,
    EvidenceError,
    GitError,
    LockfileError,
    PolicySourceError,
    PresetError,
    PresetNotFoundError,
    RepoBoundaryError,
    ReportError,
    RuleValidationError,
)


def _read_source_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        project_metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    except (FileNotFoundError, KeyError, OSError, tomllib.TOMLDecodeError):
        return "0.0.0"

    source_version = project_metadata.get("version")
    return source_version if isinstance(source_version, str) else "0.0.0"


try:
    __version__ = version("claude-md-compiler")
except PackageNotFoundError:
    __version__ = _read_source_version()


__all__ = [
    "CldcError",
    "EvidenceError",
    "GitError",
    "LockfileError",
    "PolicySourceError",
    "PresetError",
    "PresetNotFoundError",
    "RepoBoundaryError",
    "ReportError",
    "RuleValidationError",
    "__version__",
]
