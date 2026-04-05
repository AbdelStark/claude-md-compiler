from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from cldc import __version__
from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy
from cldc.runtime.evaluator import check_repo_policy
from cldc.runtime.events import EMPTY_EXECUTION_INPUTS, load_execution_inputs_file, load_execution_inputs_text
from cldc.runtime.git import collect_git_write_paths


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON output")



def _add_runtime_input_flags(parser: argparse.ArgumentParser, *, include_write: bool) -> None:
    parser.add_argument("--read", action="append", default=[], dest="read_paths", help="Path read before editing; repeat for multiple paths")
    if include_write:
        parser.add_argument("--write", action="append", default=[], dest="write_paths", help="Path written or otherwise touched; repeat for multiple paths")
    parser.add_argument("--command", action="append", default=[], dest="commands", help="Executed command string; repeat for multiple commands")
    parser.add_argument("--events-file", dest="events_file", help="Load execution input JSON from a file and merge it with explicit runtime flags")
    parser.add_argument("--stdin-json", action="store_true", dest="stdin_json", help="Load execution input JSON from stdin and merge it with explicit runtime flags")



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cldc",
        description="Compile and enforce repository policy derived from CLAUDE.md.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile repo policy into a lockfile",
        description="Parse CLAUDE.md, compiler config, and policy fragments into .claude/policy.lock.json.",
    )
    compile_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_json_flag(compile_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Inspect policy discovery and validation state",
        description="Validate discovery, source parsing, and lockfile health for a repository policy.",
    )
    doctor_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    _add_json_flag(doctor_parser)

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
    return parser


def _print_compile_result(compiled, json_output: bool) -> None:
    if json_output:
        print(json.dumps(compiled.to_dict(), indent=2, sort_keys=True))
        return
    print(
        f"Compiled {compiled.rule_count} rules from {compiled.source_count} sources into "
        f"{compiled.lockfile_path} for {compiled.repo_root}"
    )
    print(f"Default mode: {compiled.default_mode}")
    print(f"Source digest: {compiled.source_digest}")
    if compiled.warnings:
        print("Discovery warnings:")
        for warning in compiled.warnings:
            print(f"- {warning}")


def _print_doctor_result(report, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return

    status = "healthy" if not report.errors else "broken"
    print(f"Doctor status: {status}")
    print(f"Repo root: {report.repo_root}")
    print(f"Sources: {report.source_count}")
    print(f"Rules: {report.rule_count}")
    print(f"Default mode: {report.default_mode or 'n/a'}")
    if report.source_digest:
        print(f"Current source digest: {report.source_digest}")
    print(
        f"Lockfile: {report.lockfile_path} ({'present' if report.lockfile_exists else 'missing'})"
    )
    if report.lockfile_schema or report.lockfile_format_version or report.lockfile_source_digest:
        metadata_bits = [
            f"schema={report.lockfile_schema or 'unknown'}",
            f"format_version={report.lockfile_format_version or 'unknown'}",
        ]
        if report.lockfile_source_digest:
            metadata_bits.append(f"source_digest={report.lockfile_source_digest}")
        print("Lockfile metadata: " + ", ".join(metadata_bits))
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")
    if report.errors:
        print("Errors:")
        for error in report.errors:
            print(f"- {error}")
    if report.next_action:
        print(f"Recommended next action: {report.next_action}")


def _check_payload(report, git_metadata: dict[str, object] | None = None) -> dict[str, object]:
    payload = report.to_dict()
    if git_metadata is not None:
        payload['git'] = git_metadata
    return payload



def _print_check_result(report, json_output: bool, *, git_metadata: dict[str, object] | None = None) -> None:
    if json_output:
        print(json.dumps(_check_payload(report, git_metadata), indent=2, sort_keys=True))
        return

    if git_metadata is not None:
        if git_metadata.get('mode') == 'staged':
            print(f"Git input: staged diff ({git_metadata.get('write_path_count', 0)} changed paths)")
        else:
            print(
                f"Git input: {git_metadata.get('base')}...{git_metadata.get('head')} "
                f"({git_metadata.get('write_path_count', 0)} changed paths)"
            )
    print(f"Policy check: {report.decision}")
    print(f"Repo root: {report.repo_root}")
    print(f"Default mode: {report.default_mode}")
    print(
        f"Inputs: reads={len(report.inputs['read_paths'])}, writes={len(report.inputs['write_paths'])}, "
        f"commands={len(report.inputs['commands'])}, claims={len(report.inputs.get('claims', []))}"
    )
    print(
        f"Violations: {report.violation_count} total ({report.blocking_violation_count} blocking)"
    )
    for violation in report.violations:
        print(f"- [{violation.mode}] {violation.rule_id} ({violation.kind}): {violation.message}")
        if violation.matched_paths:
            print(f"  matched paths: {', '.join(violation.matched_paths)}")
        if violation.required_paths:
            print(f"  required reads: {', '.join(violation.required_paths)}")
        if violation.required_commands:
            print(f"  required commands: {', '.join(violation.required_commands)}")


def _load_cli_event_payload(args) -> dict[str, list[str]] | None:
    merged = EMPTY_EXECUTION_INPUTS

    if getattr(args, 'events_file', None):
        merged = merged.merged_with(load_execution_inputs_file(args.events_file))
    if getattr(args, 'stdin_json', False):
        merged = merged.merged_with(load_execution_inputs_text(sys.stdin.read(), source='stdin'))

    if merged == EMPTY_EXECUTION_INPUTS:
        return None
    return {
        'read_paths': merged.read_paths,
        'write_paths': merged.write_paths,
        'commands': merged.commands,
        'claims': merged.claims,
    }



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "compile":
            compiled = compile_repo_policy(Path(args.repo))
            _print_compile_result(compiled, args.json_output)
            return 0
        if args.command == "doctor":
            report = doctor_repo_policy(Path(args.repo))
            _print_doctor_result(report, args.json_output)
            return 1 if report.errors else 0
        if args.command == "check":
            report = check_repo_policy(
                Path(args.repo),
                read_paths=args.read_paths,
                write_paths=args.write_paths,
                commands=args.commands,
                event_payload=_load_cli_event_payload(args),
            )
            _print_check_result(report, args.json_output)
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
                event_payload=_load_cli_event_payload(args),
            )
            _print_check_result(report, args.json_output, git_metadata=git_metadata)
            return 2 if report.blocking_violation_count else 0
    except Exception as exc:
        if getattr(args, "json_output", False):
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "ok": False,
                        "error": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        else:
            print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
