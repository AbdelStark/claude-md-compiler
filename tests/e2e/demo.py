"""Narrated end-to-end demo runner for the langchain policy translation."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents
from cldc.runtime.evaluator import CheckReport, check_repo_policy
from cldc.runtime.remediation import build_fix_plan, render_fix_plan
from cldc.runtime.reporting import render_check_report
from .shared import LANGCHAIN_URL, LangchainE2EError, clone_langchain_repo, install_policy_translation

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None
    tty = None


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"


@dataclass(frozen=True)
class Scenario:
    """One narrated runtime-evaluation example in the demo flow."""

    label: str
    title: str
    explanation: str
    expected_decision: str
    evidence: dict[str, list[str]]
    required_rule_ids: tuple[str, ...]


class DemoUI:
    """Small ANSI-based terminal presenter for the narrated demo."""

    def __init__(self, *, color: bool, interactive: bool, pause_seconds: float) -> None:
        self.color = color
        self.interactive = interactive
        self.pause_seconds = max(0.0, pause_seconds)

    def _paint(self, text: str, *styles: str) -> str:
        if not self.color or not styles:
            return text
        return "".join(styles) + text + ANSI_RESET

    def banner(self, title: str, subtitle: str) -> None:
        line = "=" * 78
        print(self._paint(line, ANSI_CYAN))
        print(self._paint(title, ANSI_BOLD, ANSI_CYAN))
        print(self._paint(subtitle, ANSI_DIM))
        print(self._paint(line, ANSI_CYAN))

    def divider(self, *, style: str = ANSI_CYAN) -> None:
        print(self._paint("-" * 78, style))

    def section(
        self,
        index: int,
        total: int,
        title: str,
        explanation: str,
        *,
        stage: str,
        code_path: str,
        consumes: str,
        produces: str,
        cli_equivalent: str | None = None,
    ) -> None:
        print()
        self.divider(style=ANSI_BLUE)
        heading = f"[STEP {index}/{total}] {title}"
        print(self._paint(heading, ANSI_BOLD, ANSI_BLUE))
        print(explanation)
        self.bullet("pipeline stage", stage, style=ANSI_CYAN)
        self.bullet("code path", code_path)
        self.bullet("consumes", consumes)
        self.bullet("produces", produces)
        if cli_equivalent:
            print(self._paint(f"CLI equivalent: {cli_equivalent}", ANSI_DIM))

    def bullet(self, label: str, value: str, *, style: str | None = None) -> None:
        rendered_label = self._paint(label, ANSI_BOLD)
        rendered_value = self._paint(value, style) if style else value
        print(f"  - {rendered_label}: {rendered_value}")

    def note(self, text: str) -> None:
        print(self._paint(text, ANSI_DIM))

    def status(self, text: str, *, decision: str | None = None) -> None:
        style = None
        if decision == "pass":
            style = ANSI_GREEN
        elif decision == "warn":
            style = ANSI_YELLOW
        elif decision == "block":
            style = ANSI_RED
        elif decision == "info":
            style = ANSI_CYAN
        if style:
            print(self._paint(text, ANSI_BOLD, style))
            return
        print(self._paint(text, ANSI_BOLD))

    def block(self, title: str, text: str) -> None:
        print(self._paint(title, ANSI_BOLD, ANSI_MAGENTA))
        for line in text.rstrip().splitlines():
            print(f"    {line}")

    def _read_single_key(self) -> None:
        if termios is None or tty is None or not sys.stdin.isatty():
            try:
                input()
            except EOFError:
                return
            return

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print()

    def pause(self) -> None:
        if self.interactive:
            prompt = self._paint("Press any key to continue...", ANSI_DIM)
            print(f"{prompt} ", end="", flush=True)
            self._read_single_key()
            return
        if self.pause_seconds > 0:
            time.sleep(self.pause_seconds)


def _decision_style(decision: str) -> str | None:
    if decision == "pass":
        return ANSI_GREEN
    if decision == "warn":
        return ANSI_YELLOW
    if decision == "block":
        return ANSI_RED
    return None


def _format_values(values: list[str]) -> str:
    if not values:
        return "<none>"
    if len(values) == 1:
        return values[0]
    return ", ".join(values)


def _short_sha(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _check_cli_equivalent(evidence: dict[str, list[str]]) -> str:
    parts = ["cldc check <langchain-demo>"]
    for path in evidence.get("read_paths", []):
        parts.extend(["--read", path])
    for path in evidence.get("write_paths", []):
        parts.extend(["--write", path])
    for command in evidence.get("commands", []):
        parts.extend(["--command", command])
    for claim in evidence.get("claims", []):
        parts.extend(["--claim", claim])
    return " ".join(parts)


def _auto_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="cldc-e2e-demo-")).resolve()


def _explicit_workdir(path: str) -> Path:
    target = Path(path).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise LangchainE2EError(f"workdir must be empty before the demo runs: {target}")
    return target


def _prepare_workdir(args: argparse.Namespace) -> tuple[Path, bool]:
    if args.workdir:
        return _explicit_workdir(args.workdir), False
    return _auto_workdir(), True


def _source_key(path: str, block_id: str | None) -> str:
    if block_id:
        return f"{path}#{block_id}"
    return path


def _print_pipeline_map(ui: DemoUI) -> None:
    ui.block(
        "Pipeline map",
        "\n".join(
            [
                "1. Clone    -> create a real upstream workspace",
                "2. Ingest   -> discover Claude context, compiler config, and presets",
                "3. Parse    -> normalize structured rules into the internal policy model",
                "4. Compile  -> write .claude/policy.lock.json with a deterministic digest",
                "5. Evaluate -> run explicit runtime evidence through the compiled policy",
                "6. Evaluate -> show the fully-satisfied green path",
                "7. Doctor   -> inspect artifact health, freshness, and advisories",
                "8. Fix      -> generate a deterministic remediation plan from a failing report",
            ]
        ),
    )
    ui.block(
        "Decision legend",
        "\n".join(
            [
                "PASS  = all required invariants are satisfied",
                "WARN  = advisory invariants fired, but no blocking rule failed",
                "BLOCK = one or more blocking invariants failed",
            ]
        ),
    )


def _print_discovery_summary(ui: DemoUI, bundle) -> None:
    ui.bullet("discovered sources", str(len(bundle.sources)))
    print()
    print(ui._paint("  Discovery inventory", ANSI_BOLD, ANSI_MAGENTA))
    for source in bundle.sources:
        if source.kind == "claude_md":
            detail = "context source; plain prose is discovered but not semantically compiled yet"
        elif source.kind == "compiler_config":
            detail = "structured policy authoring surface; this is where the langchain translation lives"
        elif source.kind == "preset":
            detail = "bundled preset pulled in via extends:; contributes reusable workflow rules"
        elif source.kind == "inline_block":
            detail = "inline cldc fenced block; authored policy colocated with prose context"
        else:
            detail = "additional structured policy file"
        print(f"    - [{source.kind}] {_source_key(source.path, source.block_id)}")
        print(f"      {detail}")


def _print_parse_summary(ui: DemoUI, parsed) -> None:
    rules_by_source = Counter(_source_key(rule.source_path or "<unknown>", rule.source_block_id) for rule in parsed.rules)
    rules_by_kind = Counter(rule.kind for rule in parsed.rules)

    ui.bullet("default_mode", parsed.default_mode)
    ui.bullet("normalized rules", str(len(parsed.rules)))
    print()
    print(ui._paint("  Rules by source", ANSI_BOLD, ANSI_MAGENTA))
    for source_key, count in sorted(rules_by_source.items()):
        print(f"    - {source_key}: {count}")
    print()
    print(ui._paint("  Rule inventory by kind", ANSI_BOLD, ANSI_MAGENTA))
    for kind, count in sorted(rules_by_kind.items()):
        print(f"    - {kind}: {count}")
    print()
    print(ui._paint("  Structured rules", ANSI_BOLD, ANSI_MAGENTA))
    for rule in parsed.rules:
        mode = rule.mode or parsed.default_mode
        print(f"    - {rule.rule_id} [{rule.kind} / {mode}] from {_source_key(rule.source_path or '<unknown>', rule.source_block_id)}")


def _print_compile_summary(ui: DemoUI, compiled) -> None:
    ui.bullet("lockfile", compiled.lockfile_path)
    ui.bullet("compiler version", compiled.compiler_version)
    ui.bullet("default_mode", compiled.default_mode)
    ui.bullet("source count", str(compiled.source_count))
    ui.bullet("rule count", str(compiled.rule_count))
    ui.bullet("source digest", compiled.source_digest[:16] + "...")


def _run_scenario(ui: DemoUI, repo_root: Path, scenario: Scenario) -> CheckReport:
    print()
    ui.status(f"{scenario.label}: {scenario.title}", decision=scenario.expected_decision)
    print(scenario.explanation)
    ui.note(_check_cli_equivalent(scenario.evidence))
    ui.bullet("reads", _format_values(scenario.evidence.get("read_paths", [])))
    ui.bullet("writes", _format_values(scenario.evidence.get("write_paths", [])))
    ui.bullet("commands", _format_values(scenario.evidence.get("commands", [])))
    ui.bullet("claims", _format_values(scenario.evidence.get("claims", [])))

    report = check_repo_policy(repo_root, **scenario.evidence)
    fired = {violation.rule_id for violation in report.violations}
    missing = sorted(set(scenario.required_rule_ids) - fired)
    if report.decision != scenario.expected_decision:
        raise AssertionError(f"{scenario.label} expected {scenario.expected_decision!r}, got {report.decision!r}")
    if missing:
        raise AssertionError(f"{scenario.label} did not fire expected rules: {', '.join(missing)}")

    decision_style = _decision_style(report.decision)
    ui.bullet("decision", report.decision.upper(), style=decision_style)
    ui.bullet("violations", str(report.violation_count))
    if report.violations:
        ui.bullet("fired rules", ", ".join(violation.rule_id for violation in report.violations))
    ui.block("  Rendered report", render_check_report(report.to_dict()))
    return report


def _print_doctor_summary(ui: DemoUI, doctor) -> None:
    if doctor.errors:
        ui.status(f"Doctor verdict: {len(doctor.errors)} error(s)", decision="block")
    elif doctor.warnings:
        ui.status(f"Doctor verdict: healthy with {len(doctor.warnings)} advisory warning(s)", decision="info")
    else:
        ui.status("Doctor verdict: healthy", decision="pass")
    ui.bullet("discovered", str(doctor.discovered))
    ui.bullet("lockfile exists", str(doctor.lockfile_exists))
    ui.bullet("rule count", str(doctor.rule_count))
    ui.bullet("default_mode", doctor.default_mode or "<none>")
    ui.bullet("advisory warnings", str(len(doctor.warnings)))
    ui.bullet("errors", str(len(doctor.errors)))
    if doctor.warnings:
        print()
        print(ui._paint("  Advisory warnings", ANSI_BOLD, ANSI_MAGENTA))
        for warning in doctor.warnings:
            print(f"    - {warning}")
    if doctor.next_action:
        ui.bullet("next action", doctor.next_action)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a narrated end-to-end cldc demo against langchain-ai/langchain. "
            "This is the screen-recording-friendly companion to the raw pytest e2e suite."
        )
    )
    parser.add_argument("--interactive", action="store_true", help="Wait for a keypress between major stages instead of sleeping")
    parser.add_argument("--pause-seconds", type=float, default=1.25, help="Automatic pause between stages when not interactive")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("--keep-workdir", action="store_true", help="Keep the demo workspace on disk after a successful run")
    parser.add_argument("--workdir", help="Use an explicit empty directory for the demo workspace")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ui = DemoUI(color=(not args.no_color and sys.stdout.isatty()), interactive=args.interactive, pause_seconds=args.pause_seconds)
    workdir, auto_cleanup_candidate = _prepare_workdir(args)
    keep_workdir = args.keep_workdir or not auto_cleanup_candidate
    repo_root = workdir / "langchain"
    preserved_on_failure = False

    scenarios = [
        Scenario(
            label="RED 1",
            title="Edit core source without a matching test update",
            explanation=(
                "This hits two blocking invariants in one pass: the source change must be coupled "
                "with a tests/ change, and the AI-disclosure claim is still missing."
            ),
            expected_decision="block",
            evidence={"write_paths": ["libs/core/langchain_core/agents.py"]},
            required_rule_ids=("langchain-tests-follow-core-source", "langchain-require-ai-disclosure"),
        ),
        Scenario(
            label="RED 2",
            title="Write generated output under dist/",
            explanation=(
                "This comes from the bundled `default` preset, not from the hand-authored langchain "
                "translation. It shows how presets contribute real enforcement."
            ),
            expected_decision="block",
            evidence={"write_paths": ["libs/core/dist/langchain_core-0.0.0.tar.gz"]},
            required_rule_ids=("preset-default-generated-read-only",),
        ),
        Scenario(
            label="RED 3",
            title="Satisfy block rules but skip advisory read + test command",
            explanation=(
                "The change includes the companion test file and the disclosure claim, but omits the "
                "manifest read and validation command, so the decision downgrades to warn."
            ),
            expected_decision="warn",
            evidence={
                "write_paths": [
                    "libs/core/langchain_core/agents.py",
                    "libs/core/tests/unit_tests/test_agents.py",
                ],
                "claims": ["ai-agent-disclosed"],
            },
            required_rule_ids=("langchain-read-manifest-before-core-edit", "langchain-run-unit-tests-before-finish"),
        ),
    ]

    ui.banner(
        "cldc End-to-End Demo",
        "A narrated Claude policy pipeline walkthrough against langchain-ai/langchain.",
    )
    ui.bullet("upstream repo", LANGCHAIN_URL)
    ui.bullet("policy translation", "tests/e2e/compiler.yaml -> .claude-compiler.yaml")
    ui.bullet("workspace", str(workdir))
    ui.bullet("interactive mode", "on" if args.interactive else "off")
    ui.bullet("automatic pause", "disabled" if args.interactive else f"{ui.pause_seconds:.2f}s")
    ui.note("Raw regression suite still exists as `make e2e-test` / `uv run pytest -m e2e -v`.")
    print()
    _print_pipeline_map(ui)
    ui.pause()

    try:
        ui.section(
            1,
            8,
            "Clone the upstream repository",
            "Bootstrap a real repo so the demo exercises the same file layout and authored Claude context that a user would see.",
            stage="CLONE",
            code_path="git clone",
            consumes="upstream repo URL",
            produces="local langchain worktree with real CLAUDE.md context",
            cli_equivalent=f"git clone --depth=1 --filter=blob:none --single-branch {LANGCHAIN_URL}",
        )
        clone_langchain_repo(repo_root)
        ui.bullet("cloned repo", str(repo_root))
        ui.bullet("upstream commit", _short_sha(repo_root))
        ui.bullet("upstream CLAUDE.md", str(repo_root / "CLAUDE.md"))
        ui.status("Step output: workspace is ready for policy translation.", decision="info")
        ui.pause()

        bundle = None
        parsed = None

        ui.section(
            2,
            8,
            "Install the structured policy translation and discover policy sources",
            ("Ingest stage: find the authored Claude context, the explicit compiler config, and any preset packs that the config extends."),
            stage="INGEST",
            code_path="cldc.ingest.source_loader.load_policy_sources",
            consumes="repo root + CLAUDE.md + .claude-compiler.yaml",
            produces="discovered source bundle",
            cli_equivalent="cldc compile <langchain-demo>  # discovery happens before compilation",
        )
        policy_target = install_policy_translation(repo_root)
        ui.bullet("installed policy", str(policy_target))
        bundle = load_policy_sources(repo_root)
        _print_discovery_summary(ui, bundle)
        ui.status("Step output: source discovery is complete.", decision="info")
        ui.pause()

        ui.section(
            3,
            8,
            "Parse the structured policy into normalized rules",
            (
                "Parse stage: convert structured config and preset content into the normalized policy "
                "model that the compiler and runtime evaluator consume."
            ),
            stage="PARSE",
            code_path="cldc.parser.rule_parser.parse_rule_documents",
            consumes="discovered source bundle",
            produces="normalized rule set + default mode",
            cli_equivalent="cldc compile <langchain-demo>  # parsing happens during compilation",
        )
        assert bundle is not None
        parsed = parse_rule_documents(bundle)
        _print_parse_summary(ui, parsed)
        ui.status("Step output: structured rules are normalized and ready to compile.", decision="info")
        ui.pause()

        ui.section(
            4,
            8,
            "Compile the deterministic lockfile artifact",
            ("Compile stage: hash the source bundle, freeze deterministic metadata, and materialize `.claude/policy.lock.json`."),
            stage="COMPILE",
            code_path="cldc.compiler.policy_compiler.compile_repo_policy",
            consumes="normalized policy inputs + repo root",
            produces=".claude/policy.lock.json",
            cli_equivalent="cldc compile <langchain-demo>",
        )
        compiled = compile_repo_policy(repo_root)
        _print_compile_summary(ui, compiled)
        ui.status("Step output: the lockfile contract is on disk.", decision="info")
        ui.pause()

        ui.section(
            5,
            8,
            "Run red scenarios against the compiled policy",
            ("Runtime stage: judge explicit evidence against the compiled lockfile and surface every violated rule in a single pass."),
            stage="EVALUATE (RED PATHS)",
            code_path="cldc.runtime.evaluator.check_repo_policy",
            consumes="explicit runtime evidence + compiled lockfile",
            produces="CheckReport with pass/warn/block decision",
            cli_equivalent="cldc check <langchain-demo> ...",
        )
        first_red_report: CheckReport | None = None
        for scenario in scenarios:
            report = _run_scenario(ui, repo_root, scenario)
            if first_red_report is None:
                first_red_report = report
            ui.pause()

        ui.section(
            6,
            8,
            "Run a green scenario that satisfies every rule",
            (
                "A complete evidence set reads the manifest, edits source and tests together, "
                "runs validation, and records the required claim."
            ),
            stage="EVALUATE (GREEN PATH)",
            code_path="cldc.runtime.evaluator.check_repo_policy",
            consumes="complete evidence set",
            produces="clean passing CheckReport",
            cli_equivalent=(
                "cldc check <langchain-demo> --read libs/core/pyproject.toml "
                "--write libs/core/langchain_core/agents.py "
                "--write libs/core/tests/unit_tests/test_agents.py "
                "--command 'make test' --claim ai-agent-disclosed"
            ),
        )
        green_report = check_repo_policy(
            repo_root,
            read_paths=["libs/core/pyproject.toml"],
            write_paths=[
                "libs/core/langchain_core/agents.py",
                "libs/core/tests/unit_tests/test_agents.py",
            ],
            commands=["make test"],
            claims=["ai-agent-disclosed"],
        )
        if green_report.decision != "pass" or green_report.violations:
            raise AssertionError(f"green scenario should pass cleanly, got {green_report.decision!r}")
        ui.bullet("decision", green_report.decision.upper(), style=_decision_style(green_report.decision))
        ui.bullet("violations", str(green_report.violation_count))
        ui.block("  Rendered report", render_check_report(green_report.to_dict()))
        ui.pause()

        ui.section(
            7,
            8,
            "Run doctor for artifact health and advisories",
            (
                "Doctor stage: verify that discovery, parsing, and the compiled artifact are still aligned. "
                "Warnings are advisory; errors indicate a broken or stale artifact."
            ),
            stage="DOCTOR",
            code_path="cldc.compiler.policy_compiler.doctor_repo_policy",
            consumes="repo root + compiled lockfile",
            produces="health report with errors, warnings, and next action",
            cli_equivalent="cldc doctor <langchain-demo>",
        )
        doctor = doctor_repo_policy(repo_root)
        if doctor.errors:
            raise AssertionError(f"doctor should be healthy after compile, got errors: {doctor.errors}")
        _print_doctor_summary(ui, doctor)
        ui.pause()

        ui.section(
            8,
            8,
            "Generate a deterministic fix plan from the first failing report",
            (
                "Remediation stage (`cldc.runtime.remediation.build_fix_plan`): turn a saved report into explicit "
                "next steps, files to inspect, and claims or commands that are still missing."
            ),
            stage="FIX",
            code_path="cldc.runtime.remediation.build_fix_plan",
            consumes="saved failing CheckReport",
            produces="deterministic remediation plan",
            cli_equivalent="cldc fix <langchain-demo> --report-file policy-report.json",
        )
        assert first_red_report is not None
        fix_plan = build_fix_plan(first_red_report.to_dict())
        ui.bullet("decision", fix_plan["decision"].upper(), style=_decision_style(fix_plan["decision"]))
        ui.bullet("remediations", str(fix_plan["remediation_count"]))
        if fix_plan.get("next_action"):
            ui.bullet("next action", fix_plan["next_action"])
        ui.block("  Rendered fix plan", render_fix_plan(fix_plan))
        ui.pause()

        print()
        ui.status("Demo complete: the full pipeline executed successfully.", decision="pass")
        ui.note("Use `make e2e-interactive` for manual stepping or `make e2e-test` for the raw pytest suite.")
    except LangchainE2EError as exc:
        preserved_on_failure = True
        print()
        ui.status(f"Demo setup failed: {exc}", decision="block")
        ui.note(f"Workspace preserved at {workdir}")
        return 1
    except Exception:
        preserved_on_failure = True
        print()
        ui.status("Demo failed with an unexpected error.", decision="block")
        ui.note(f"Workspace preserved at {workdir}")
        raise
    finally:
        if auto_cleanup_candidate and not keep_workdir and not preserved_on_failure and workdir.exists():
            shutil.rmtree(workdir)
            ui.note("Cleaned up the temporary demo workspace.")
        elif workdir.exists():
            ui.note(f"Workspace available at {workdir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
