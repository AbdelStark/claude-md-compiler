from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from cldc.compiler.policy_compiler import compile_repo_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cldc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile", help="Compile repo policy into a lockfile")
    compile_parser.add_argument("repo", nargs="?", default=".")
    compile_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "compile":
            compiled = compile_repo_policy(Path(args.repo))
            if args.json_output:
                print(json.dumps(compiled.__dict__, indent=2, sort_keys=True))
            else:
                print(
                    f"Compiled {compiled.rule_count} rules into {compiled.lockfile_path} "
                    f"for {compiled.repo_root}"
                )
            return 0
    except Exception as exc:
        print(f"compile failed: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
