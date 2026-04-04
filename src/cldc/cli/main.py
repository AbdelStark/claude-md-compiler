from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cldc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile", help="Compile repo policy into a lockfile")
    compile_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    compile_parser.add_argument("--json", action="store_true", dest="json_output")

    doctor_parser = subparsers.add_parser("doctor", help="Inspect policy discovery and validation state")
    doctor_parser.add_argument("repo", nargs="?", default=".", help="Repo root or any path inside the repo")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _print_compile_result(compiled, json_output: bool) -> None:
    if json_output:
        print(json.dumps(compiled.to_dict(), indent=2, sort_keys=True))
        return
    print(
        f"Compiled {compiled.rule_count} rules from {compiled.source_count} sources into "
        f"{compiled.lockfile_path} for {compiled.repo_root}"
    )


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
    print(
        f"Lockfile: {report.lockfile_path} ({'present' if report.lockfile_exists else 'missing'})"
    )
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")
    if report.errors:
        print("Errors:")
        for error in report.errors:
            print(f"- {error}")


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
    except Exception as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
