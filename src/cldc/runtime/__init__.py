"""Runtime layer for cldc.

Re-exports the small set of public symbols that downstream embedders need to
evaluate policy, build remediation plans, and integrate with git. Importing
from `cldc.runtime` gives a stable surface even if internal modules are
restructured later.
"""

from cldc.runtime.evaluator import CheckReport, Violation, check_repo_policy
from cldc.runtime.events import (
    ExecutionInputs,
    load_execution_inputs,
    load_execution_inputs_file,
    load_execution_inputs_text,
)
from cldc.runtime.git import collect_git_write_paths
from cldc.runtime.remediation import FIX_PLAN_FORMAT_VERSION, FIX_PLAN_SCHEMA, build_fix_plan, render_fix_plan

__all__ = [
    "FIX_PLAN_FORMAT_VERSION",
    "FIX_PLAN_SCHEMA",
    "CheckReport",
    "ExecutionInputs",
    "Violation",
    "build_fix_plan",
    "check_repo_policy",
    "collect_git_write_paths",
    "load_execution_inputs",
    "load_execution_inputs_file",
    "load_execution_inputs_text",
    "render_fix_plan",
]
