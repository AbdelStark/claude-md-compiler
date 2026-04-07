"""Typed exception hierarchy for cldc.

All library errors inherit from `CldcError`, which itself inherits from
`ValueError` so existing consumers that catch `ValueError` continue to work.
Catch `CldcError` (or a specific subclass) in new code for finer control.
"""

from __future__ import annotations


class CldcError(ValueError):
    """Base class for all errors raised by cldc."""


class PolicySourceError(CldcError):
    """Raised for malformed policy source files (CLAUDE.md, .claude-compiler.yaml, policies/*.yml)."""


class RuleValidationError(CldcError):
    """Raised when a rule document fails validation (missing kind, duplicate id, etc.)."""


class LockfileError(CldcError):
    """Raised when the compiled lockfile is malformed, stale, or schema-drifted."""


class EvidenceError(CldcError):
    """Raised when an execution-input / event payload fails validation."""


class ReportError(CldcError):
    """Raised when a saved check report or fix plan fails validation."""


class PresetError(CldcError):
    """Raised when a bundled preset cannot be loaded or resolved."""


class PresetNotFoundError(PresetError, LookupError):
    """Raised when a requested preset name is not bundled with cldc."""


class RepoBoundaryError(CldcError):
    """Raised when a runtime evidence path resolves outside the repo root."""


class GitError(CldcError):
    """Raised when a `git` invocation or argument combination fails during `cldc ci`."""
