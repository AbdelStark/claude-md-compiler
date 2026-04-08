"""Argparse-based command-line entry point for `cldc`.

`main(argv)` is the single function the `cldc` console script invokes. It
builds the parser, dispatches to the appropriate library call in
`cldc.compiler`, `cldc.runtime`, `cldc.presets`, `cldc.scaffold`, or
`cldc.tui`, and translates the result into a shell-friendly exit code:

* `0` — clean run, or a non-blocking decision (`pass`/`warn`).
* `1` — runtime or input error (`--json` payload includes `error_type`).
* `2` — at least one blocking policy violation (`block`).

This module is intentionally a thin shell. All policy-relevant behavior lives
in the library layers; this file translates argparse namespaces into library
calls and library results into stdout/stderr text or JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cldc import __version__
from cldc._logging import configure_cli_logging
from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy
from cldc.presets import list_presets, load_preset, preset_path
from cldc.runtime.claude_code_adapter import (
    record_claude_claim,
    run_post_tool_use,
    run_pre_tool_use,
    run_session_end,
    run_session_start,
    run_stop,
)
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.events import EMPTY_EXECUTION_INPUTS, load_execution_inputs_file, load_execution_inputs_text
from cldc.runtime.git import collect_git_write_paths
from cldc.runtime.hooks import (
    INSTALLABLE_HOOK_KINDS,
    SUPPORTED_HOOK_KINDS,
    generate_hook,
    install_hook,
)
from cldc.runtime.remediation import build_fix_plan, render_fix_plan
from cldc.runtime.reporting import load_check_report_file, load_check_report_text, render_check_report
from cldc.scaffold import initialize_repo_policy


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON output")


def _add_output_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        dest="output_path",
        help="Also write the command output to a file (creates parent directories when needed)",
    )


def _add_runtime_input_flags(parser: argparse.ArgumentParser, *, include_write: bool) -> None:
    parser.add_argument(
        "--read", action="append", default=[], dest="read_paths", help="Path read before editing; repeat for multiple paths"
    )
    if include_write:
        parser.add_argument(
            "--write", action="append", default=[], dest="write_paths", help="Path written or otherwise touched; repeat for multiple paths"
        )
    parser.add_argument(
        "--command", action="append", default=[], dest="commands", help="Executed command string; repeat for multiple commands"
    )
    parser.add_argument(
        "--claim",
        action="append",
        default=[],
        dest="claims",
        help="Asserted policy claim (for example 'qa-reviewed'); repeat for multiple claims",
    )
    parser.add_argument(
        "--events-file", dest="events_file", help="Load execution input JSON from a file and merge it with explicit runtime flags"
    )
    parser.add_argument(
        "--stdin-json",
        action="store_true",
        dest="stdin_json",
        help="Load execution input JSON from stdin and merge it with explicit runtime flags",
    )


def _add_report_input_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--report-file", dest="report_file", help="Load an existing JSON policy report and render it without re-running evaluation"
    )
    parser.add_argument(
        "--stdin-report",
        action="store_true",
        dest="stdin_report",
        help="Load an existing JSON policy report from stdin and render it without re-running evaluation",
    )
    parser.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="Render format for non-JSON explain output (default: text)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the `cldc` argument parser and all command subparsers."""

    parser = argparse.ArgumentParser(
        prog="cldc",
        description="Compile and enforce repository policy derived from CLAUDE.md.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=("Emit debug-level diagnostics to stderr. Place before the subcommand (for example `cldc --verbose compile .`)."),
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help=(
            "Suppress warnings and info output, leaving only errors. Place before the subcommand (for example `cldc --quiet compile .`)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold .claude-compiler.yaml (and a stub CLAUDE.md) for a new repo",
        description=(
            "Scaffold a minimal `.claude-compiler.yaml` that extends one or more "
            "bundled presets. Also writes a stub `CLAUDE.md` if none exists. "
            "Never overwrites an existing `CLAUDE.md`; refuses to overwrite an "
            "existing `.claude-compiler.yaml` unless --force is passed."
        ),
    )
    init_parser.add_argument("repo", nargs="?", default=".", help="Target repo root (must exist)")
    init_parser.add_argument(
        "--preset",
        action="append",
        default=None,
        dest="init_presets",
        help="Bundled preset to extend; repeat for multiple presets (default: default)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        dest="init_force",
        help="Overwrite an existing .claude-compiler.yaml in the target repo",
    )
    _add_json_flag(init_parser)
    _add_output_flag(init_parser)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile repo policy into a lockfile",
        description="Parse CLAUDE.md, compiler config, and policy fragments into .claude/policy.lock.json.",
    )
    compile_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_json_flag(compile_parser)
    _add_output_flag(compile_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Inspect policy discovery and validation state",
        description="Validate discovery, source parsing, and lockfile health for a repository policy.",
    )
    doctor_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_json_flag(doctor_parser)
    _add_output_flag(doctor_parser)

    check_parser = subparsers.add_parser(
        "check",
        help="Evaluate runtime activity against the compiled policy",
        description=(
            "Evaluate read paths, write paths, and executed commands against the compiled policy lockfile. "
            "Paths may be repo-relative or absolute inside the discovered repo."
        ),
    )
    check_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_runtime_input_flags(check_parser, include_write=True)
    _add_json_flag(check_parser)
    _add_output_flag(check_parser)

    ci_parser = subparsers.add_parser(
        "ci",
        help="Derive changed files from git and evaluate them against the compiled policy",
        description=(
            "Collect changed files from git using staged changes or a base/head diff, then evaluate them with the compiled policy lockfile."
        ),
    )
    ci_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    ci_parser.add_argument("--staged", action="store_true", help="Evaluate files from `git diff --cached --name-only`")
    ci_parser.add_argument("--base", help="Base git ref for a range diff (for example origin/main)")
    ci_parser.add_argument("--head", help="Head git ref for a range diff (defaults to HEAD when --base is provided)")
    _add_runtime_input_flags(ci_parser, include_write=False)
    _add_json_flag(ci_parser)
    _add_output_flag(ci_parser)

    explain_parser = subparsers.add_parser(
        "explain",
        help="Render an explainable policy report from saved JSON or fresh runtime evidence",
        description=(
            "Explain policy results from either a saved JSON report artifact or by evaluating fresh runtime evidence against the compiled policy lockfile."
        ),
    )
    explain_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_runtime_input_flags(explain_parser, include_write=True)
    _add_report_input_flags(explain_parser)
    _add_json_flag(explain_parser)
    _add_output_flag(explain_parser)

    fix_parser = subparsers.add_parser(
        "fix",
        help="Generate a remediation plan from saved JSON or fresh runtime evidence",
        description=(
            "Build a deterministic remediation plan from either a saved JSON policy report artifact "
            "or by evaluating fresh runtime evidence against the compiled policy lockfile."
        ),
    )
    fix_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_runtime_input_flags(fix_parser, include_write=True)
    _add_report_input_flags(fix_parser)
    _add_json_flag(fix_parser)
    _add_output_flag(fix_parser)

    preset_parser = subparsers.add_parser(
        "preset",
        help="List and show bundled policy packs that repos can extend via .claude-compiler.yaml",
        description=(
            "Inspect the policy packs bundled with this cldc version. Packs can be referenced "
            "from `.claude-compiler.yaml` via `extends: [NAME]` to merge their rules into the "
            "compiled lockfile alongside user-defined rules."
        ),
    )
    preset_subparsers = preset_parser.add_subparsers(dest="preset_command", required=True)

    preset_list_parser = preset_subparsers.add_parser(
        "list",
        help="List every bundled preset policy pack",
        description="List every bundled preset, sorted by name, with its on-disk path.",
    )
    _add_json_flag(preset_list_parser)
    _add_output_flag(preset_list_parser)

    preset_show_parser = preset_subparsers.add_parser(
        "show",
        help="Print the YAML contents of one bundled preset",
        description=("Print the raw YAML contents of one bundled preset so it can be reviewed, copied, or piped into other tools."),
    )
    preset_show_parser.add_argument("name", help="Name of the bundled preset, for example 'default'")
    _add_json_flag(preset_show_parser)
    _add_output_flag(preset_show_parser)

    hook_parser = subparsers.add_parser(
        "hook",
        help="Generate or install hook scripts that wire `cldc` into git or Claude Code",
        description=(
            "Emit hook artifacts and session-adapter helpers that wire `cldc` into git "
            "or Claude Code. `generate` prints a hook to stdout for review or "
            "redirection; `install` writes a supported hook into the repo (currently "
            "only `git-pre-commit`); `claim` appends an explicit claim to the active "
            "Claude Code session."
        ),
    )
    hook_subparsers = hook_parser.add_subparsers(dest="hook_command", required=True)

    hook_generate_parser = hook_subparsers.add_parser(
        "generate",
        help="Print a hook script to stdout",
        description="Print a hook artifact to stdout. Use shell redirection to capture it.",
    )
    hook_generate_parser.add_argument(
        "kind",
        choices=SUPPORTED_HOOK_KINDS,
        help="Which hook artifact to generate",
    )
    _add_json_flag(hook_generate_parser)
    _add_output_flag(hook_generate_parser)

    hook_install_parser = hook_subparsers.add_parser(
        "install",
        help="Write an installable hook into the repo",
        description=(
            "Write an installable hook artifact into the repo. Currently the only "
            "installable kind is `git-pre-commit`, which is written to "
            "`.git/hooks/pre-commit` and made executable."
        ),
    )
    hook_install_parser.add_argument(
        "kind",
        choices=INSTALLABLE_HOOK_KINDS,
        help="Which hook artifact to install",
    )
    hook_install_parser.add_argument("repo", nargs="?", default=".", help="Target repo root (must contain .git)")
    hook_install_parser.add_argument(
        "--force",
        action="store_true",
        dest="hook_force",
        help="Overwrite an existing hook script of the same kind",
    )
    _add_json_flag(hook_install_parser)
    _add_output_flag(hook_install_parser)

    hook_claim_parser = hook_subparsers.add_parser(
        "claim",
        help="Append an explicit claim to the active Claude Code session",
        description=(
            "Append an explicit claim (for example `ci-green`) to the active "
            "Claude Code hook session for this repo. Use --session to target a "
            "specific session id instead of the active one."
        ),
    )
    hook_claim_parser.add_argument("repo", nargs="?", default=".", help="Target repo root (must be the same repo Claude is using)")
    hook_claim_parser.add_argument("claim", help="Claim string to append to the current Claude Code session")
    hook_claim_parser.add_argument("--session", dest="hook_session", help="Specific Claude Code session id to append the claim to")
    _add_json_flag(hook_claim_parser)
    _add_output_flag(hook_claim_parser)

    hook_runtime_parser = hook_subparsers.add_parser(
        "runtime",
        help=argparse.SUPPRESS,
        description=argparse.SUPPRESS,
    )
    hook_runtime_subparsers = hook_runtime_parser.add_subparsers(dest="hook_runtime_action", required=True)
    for action in (
        "claude-session-start",
        "claude-pre-tool-use",
        "claude-post-tool-use",
        "claude-stop",
        "claude-session-end",
    ):
        runtime_action_parser = hook_runtime_subparsers.add_parser(
            action,
            help=argparse.SUPPRESS,
            description=argparse.SUPPRESS,
        )
        runtime_action_parser.add_argument("repo", help=argparse.SUPPRESS)

    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch the interactive terminal UI",
        description=(
            "Launch the interactive terminal UI (Textual-based). Loads the repo's policy, "
            "browses sources and rules, composes runtime evidence, and runs live checks "
            "against the compiled lockfile without leaving the terminal."
        ),
    )
    tui_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")

    return parser


def _output_text(text: str, output_path: str | None = None) -> None:
    print(text)
    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized_text = text if text.endswith("\n") else f"{text}\n"
        target.write_text(normalized_text, encoding="utf-8")


def _render_init_result(report, json_output: bool) -> str:
    if json_output:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Initialized cldc policy for {report.repo_root}",
        f"Extends: {', '.join(report.presets)}",
    ]
    if report.created:
        lines.append("Created:")
        lines.extend(f"- {name}" for name in report.created)
    if report.updated:
        lines.append("Updated:")
        lines.extend(f"- {name}" for name in report.updated)
    if report.skipped:
        lines.append("Skipped (already present):")
        lines.extend(f"- {name}" for name in report.skipped)
    lines.append(f"Next action: {report.next_action}")
    return "\n".join(lines)


def _render_compile_result(compiled, json_output: bool) -> str:
    if json_output:
        return json.dumps(compiled.to_dict(), indent=2, sort_keys=True)

    lines = [
        (
            f"Compiled {compiled.rule_count} rules from {compiled.source_count} sources into "
            f"{compiled.lockfile_path} for {compiled.repo_root}"
        ),
        f"Default mode: {compiled.default_mode}",
        f"Source digest: {compiled.source_digest}",
    ]
    if compiled.warnings:
        lines.append("Discovery warnings:")
        lines.extend(f"- {warning}" for warning in compiled.warnings)
    return "\n".join(lines)


def _render_doctor_result(report, json_output: bool) -> str:
    if json_output:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)

    status = "healthy" if not report.errors else "broken"
    lines = [
        f"Doctor status: {status}",
        f"Repo root: {report.repo_root}",
        f"Sources: {report.source_count}",
        f"Rules: {report.rule_count}",
        f"Default mode: {report.default_mode or 'n/a'}",
    ]
    if report.source_digest:
        lines.append(f"Current source digest: {report.source_digest}")
    lines.append(f"Lockfile: {report.lockfile_path} ({'present' if report.lockfile_exists else 'missing'})")
    if report.lockfile_schema or report.lockfile_format_version or report.lockfile_source_digest:
        metadata_bits = [
            f"schema={report.lockfile_schema or 'unknown'}",
            f"format_version={report.lockfile_format_version or 'unknown'}",
        ]
        if report.lockfile_source_digest:
            metadata_bits.append(f"source_digest={report.lockfile_source_digest}")
        lines.append("Lockfile metadata: " + ", ".join(metadata_bits))
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in report.errors)
    if report.next_action:
        lines.append(f"Recommended next action: {report.next_action}")
    return "\n".join(lines)


def _check_payload(report, git_metadata: dict[str, object] | None = None) -> dict[str, object]:
    payload = report.to_dict()
    if git_metadata is not None:
        payload["git"] = git_metadata
    return payload


def _render_check_result(report, json_output: bool, *, git_metadata: dict[str, object] | None = None) -> str:
    if json_output:
        return json.dumps(_check_payload(report, git_metadata), indent=2, sort_keys=True)

    lines: list[str] = []
    if git_metadata is not None:
        if git_metadata.get("mode") == "staged":
            lines.append(f"Git input: staged diff ({git_metadata.get('write_path_count', 0)} changed paths)")
        else:
            lines.append(
                f"Git input: {git_metadata.get('base')}...{git_metadata.get('head')} "
                f"({git_metadata.get('write_path_count', 0)} changed paths)"
            )
    lines.extend(
        [
            f"Policy check: {report.decision}",
            f"Summary: {report.summary}",
            f"Repo root: {report.repo_root}",
            f"Default mode: {report.default_mode}",
            (
                f"Inputs: reads={len(report.inputs['read_paths'])}, writes={len(report.inputs['write_paths'])}, "
                f"commands={len(report.inputs['commands'])}, claims={len(report.inputs.get('claims', []))}"
            ),
            f"Violations: {report.violation_count} total ({report.blocking_violation_count} blocking)",
        ]
    )
    if report.next_action:
        lines.append(f"Recommended next action: {report.next_action}")
    for violation in report.violations:
        lines.append(f"- [{violation.mode}] {violation.rule_id} ({violation.kind}): {violation.message}")
        lines.append(f"  why: {violation.explanation}")
        lines.append(f"  next step: {violation.recommended_action}")
        if violation.matched_paths:
            lines.append(f"  matched paths: {', '.join(violation.matched_paths)}")
        if violation.matched_commands:
            lines.append(f"  matched commands: {', '.join(violation.matched_commands)}")
        if violation.required_paths:
            lines.append(f"  required reads: {', '.join(violation.required_paths)}")
        if violation.required_commands:
            lines.append(f"  required commands: {', '.join(violation.required_commands)}")
        if violation.required_claims:
            lines.append(f"  required claims: {', '.join(violation.required_claims)}")
    return "\n".join(lines)


def _load_cli_event_payload(args) -> dict[str, list[str]] | None:
    merged = EMPTY_EXECUTION_INPUTS

    if getattr(args, "events_file", None):
        merged = merged.merged_with(load_execution_inputs_file(args.events_file))
    if getattr(args, "stdin_json", False):
        merged = merged.merged_with(load_execution_inputs_text(sys.stdin.read(), source="stdin"))

    if merged == EMPTY_EXECUTION_INPUTS:
        return None
    return {
        "read_paths": merged.read_paths,
        "write_paths": merged.write_paths,
        "commands": merged.commands,
        "claims": merged.claims,
    }


def _has_runtime_inputs(args) -> bool:
    return bool(
        getattr(args, "read_paths", None)
        or getattr(args, "write_paths", None)
        or getattr(args, "commands", None)
        or getattr(args, "claims", None)
        or getattr(args, "events_file", None)
        or getattr(args, "stdin_json", False)
    )


def _load_explain_payload(args) -> dict[str, object]:
    if getattr(args, "report_file", None) and getattr(args, "stdin_report", False):
        raise ValueError("`cldc explain` accepts only one saved report source: choose --report-file or --stdin-report")
    if getattr(args, "stdin_json", False) and getattr(args, "stdin_report", False):
        raise ValueError("`cldc explain` cannot consume both --stdin-json and --stdin-report from stdin in the same run")

    if getattr(args, "report_file", None) or getattr(args, "stdin_report", False):
        if _has_runtime_inputs(args):
            raise ValueError(
                "`cldc explain` cannot combine saved report input with fresh runtime evidence; "
                "use either --report-file/--stdin-report or the runtime evidence flags"
            )
        if getattr(args, "report_file", None):
            return load_check_report_file(args.report_file)
        return load_check_report_text(sys.stdin.read(), source="stdin")

    report = check_repo_policy(
        Path(args.repo),
        read_paths=args.read_paths,
        write_paths=args.write_paths,
        commands=args.commands,
        claims=args.claims,
        event_payload=_load_cli_event_payload(args),
    )
    return _check_payload(report)


def _render_preset_list(json_output: bool) -> str:
    presets = list_presets()
    if json_output:
        payload = {
            "preset_count": len(presets),
            "presets": [preset.to_dict() for preset in presets],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    if not presets:
        return "No presets are bundled with this cldc version."
    lines = [f"Bundled presets ({len(presets)}):"]
    for preset in presets:
        lines.append(f"- {preset.name} ({preset.path})")
    lines.append("")
    lines.append("Extend any of these from .claude-compiler.yaml:")
    lines.append("  extends:")
    lines.append(f"    - {presets[0].name}")
    return "\n".join(lines)


def _render_preset_show(name: str, json_output: bool) -> str:
    path = preset_path(name)
    content = load_preset(name)
    if json_output:
        payload = {
            "name": name,
            "path": str(path),
            "content": content,
        }
        return json.dumps(payload, indent=2, sort_keys=True)
    return content.rstrip() + "\n"


def _render_hook_generate(artifact, json_output: bool) -> str:
    if json_output:
        return json.dumps(artifact.to_dict(), indent=2, sort_keys=True)
    return artifact.content if artifact.content.endswith("\n") else artifact.content + "\n"


def _render_hook_install(report, json_output: bool) -> str:
    if json_output:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Installed {report.kind} hook ({report.action})",
        f"Repo root: {report.repo_root}",
        f"Target: {report.target_path}",
        f"Executable: {'yes' if report.executable else 'no'}",
        f"Next action: {report.next_action}",
    ]
    return "\n".join(lines)


def _render_hook_claim(report, json_output: bool) -> str:
    if json_output:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Recorded claim: {report.claim}",
        f"Repo root: {report.repo_root}",
        f"Session id: {report.session_id}",
        f"Claim count: {report.claim_count}",
        f"State file: {report.state_path}",
        f"Latest report: {report.report_path}",
    ]
    return "\n".join(lines)


def _load_fix_payload(args) -> dict[str, object]:
    if getattr(args, "report_file", None) and getattr(args, "stdin_report", False):
        raise ValueError("`cldc fix` accepts only one saved report source: choose --report-file or --stdin-report")
    if getattr(args, "stdin_json", False) and getattr(args, "stdin_report", False):
        raise ValueError("`cldc fix` cannot consume both --stdin-json and --stdin-report from stdin in the same run")

    if getattr(args, "report_file", None) or getattr(args, "stdin_report", False):
        if _has_runtime_inputs(args):
            raise ValueError(
                "`cldc fix` cannot combine saved report input with fresh runtime evidence; "
                "use either --report-file/--stdin-report or the runtime evidence flags"
            )
        if getattr(args, "report_file", None):
            report_payload = load_check_report_file(args.report_file)
        else:
            report_payload = load_check_report_text(sys.stdin.read(), source="stdin")
    else:
        report = check_repo_policy(
            Path(args.repo),
            read_paths=args.read_paths,
            write_paths=args.write_paths,
            commands=args.commands,
            claims=args.claims,
            event_payload=_load_cli_event_payload(args),
        )
        report_payload = _check_payload(report)

    return build_fix_plan(report_payload)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a shell-friendly exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    configure_cli_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        if args.command == "init":
            report = initialize_repo_policy(
                Path(args.repo),
                presets=args.init_presets,
                force=args.init_force,
            )
            _output_text(_render_init_result(report, args.json_output), args.output_path)
            return 0
        if args.command == "compile":
            compiled = compile_repo_policy(Path(args.repo))
            _output_text(_render_compile_result(compiled, args.json_output), args.output_path)
            return 0
        if args.command == "doctor":
            report = doctor_repo_policy(Path(args.repo))
            _output_text(_render_doctor_result(report, args.json_output), args.output_path)
            return 1 if report.errors else 0
        if args.command == "check":
            report = check_repo_policy(
                Path(args.repo),
                read_paths=args.read_paths,
                write_paths=args.write_paths,
                commands=args.commands,
                claims=args.claims,
                event_payload=_load_cli_event_payload(args),
            )
            _output_text(_render_check_result(report, args.json_output), args.output_path)
            return 2 if report.blocking_violation_count else 0
        if args.command == "ci":
            write_paths, git_metadata = collect_git_write_paths(
                Path(args.repo),
                staged=args.staged,
                base=args.base,
                head=args.head,
            )
            report = check_repo_policy(
                Path(args.repo),
                read_paths=args.read_paths,
                write_paths=write_paths,
                commands=args.commands,
                claims=args.claims,
                event_payload=_load_cli_event_payload(args),
            )
            _output_text(_render_check_result(report, args.json_output, git_metadata=git_metadata), args.output_path)
            return 2 if report.blocking_violation_count else 0
        if args.command == "explain":
            payload = _load_explain_payload(args)
            if args.json_output:
                rendered = json.dumps(payload, indent=2, sort_keys=True)
            else:
                rendered = render_check_report(payload, format=args.format)
            _output_text(rendered, args.output_path)
            return 0
        if args.command == "fix":
            payload = _load_fix_payload(args)
            rendered = json.dumps(payload, indent=2, sort_keys=True) if args.json_output else render_fix_plan(payload, format=args.format)
            _output_text(rendered, args.output_path)
            return 0
        if args.command == "preset":
            if args.preset_command == "list":
                _output_text(_render_preset_list(args.json_output), args.output_path)
                return 0
            if args.preset_command == "show":
                _output_text(_render_preset_show(args.name, args.json_output), args.output_path)
                return 0
            # argparse guarantees preset_command is "list" or "show"
            # because required=True + choices-as-subparsers. This branch is
            # unreachable via the CLI; keep the explicit error for
            # programmatic callers that bypass argparse.
            parser.error(f"unknown preset subcommand: {args.preset_command}")
        if args.command == "hook":
            if args.hook_command == "generate":
                artifact = generate_hook(args.kind)
                _output_text(_render_hook_generate(artifact, args.json_output), args.output_path)
                return 0
            if args.hook_command == "install":
                report = install_hook(args.kind, Path(args.repo), force=args.hook_force)
                _output_text(_render_hook_install(report, args.json_output), args.output_path)
                return 0
            if args.hook_command == "claim":
                report = record_claude_claim(
                    Path(args.repo),
                    args.claim,
                    session_id=args.hook_session,
                )
                _output_text(_render_hook_claim(report, args.json_output), args.output_path)
                return 0
            if args.hook_command == "runtime":
                payload_text = sys.stdin.read()
                if args.hook_runtime_action == "claude-session-start":
                    result = run_session_start(Path(args.repo), payload_text)
                elif args.hook_runtime_action == "claude-pre-tool-use":
                    result = run_pre_tool_use(Path(args.repo), payload_text)
                elif args.hook_runtime_action == "claude-post-tool-use":
                    result = run_post_tool_use(Path(args.repo), payload_text)
                elif args.hook_runtime_action == "claude-stop":
                    result = run_stop(Path(args.repo), payload_text)
                elif args.hook_runtime_action == "claude-session-end":
                    result = run_session_end(Path(args.repo), payload_text)
                else:
                    parser.error(f"unknown hook runtime action: {args.hook_runtime_action}")

                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                return result.exit_code
            # argparse enforces required=True; unreachable from the CLI but
            # kept as a guard for programmatic callers.
            parser.error(f"unknown hook subcommand: {args.hook_command}")
        if args.command == "tui":
            from cldc.tui import run_tui

            return run_tui(Path(args.repo))
    except Exception as exc:
        if getattr(args, "json_output", False):
            error_payload: dict[str, object] = {
                "command": args.command,
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            if getattr(args, "verbose", False):
                import traceback

                error_payload["traceback"] = traceback.format_exc().rstrip()
            print(
                json.dumps(error_payload, indent=2, sort_keys=True),
                file=sys.stderr,
            )
        else:
            print(f"{args.command} failed: {exc}", file=sys.stderr)
            if getattr(args, "verbose", False):
                import traceback

                traceback.print_exc(file=sys.stderr)
        return 1

    # argparse enforces required=True on the subcommand and every branch
    # above covers a registered subparser, so this line is unreachable via
    # the CLI. Kept as a defensive signal for programmatic callers that
    # bypass argparse and hand-build the namespace.
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
