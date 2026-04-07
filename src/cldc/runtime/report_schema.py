"""Versioned schema constants for the `policy-report/v1` JSON contract.

These constants live in their own module to break what would otherwise be a
circular import between `cldc.runtime.evaluator` (the producer) and
`cldc.runtime.reporting` (the validator/renderer). Changing them is a
breaking change to the on-disk artifact and requires a major version bump.
"""

from __future__ import annotations

CHECK_REPORT_FORMAT_VERSION = "1"
CHECK_REPORT_SCHEMA = "https://cldc.dev/schemas/policy-report/v1"
