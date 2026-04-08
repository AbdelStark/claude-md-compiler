"""Runtime policy evaluation for cldc.

`check_repo_policy` is the pure-function judge. It loads the compiled
lockfile, validates its freshness against the live policy sources, normalizes
the supplied evidence (read paths, write paths, commands, claims) into
repo-relative POSIX form, and evaluates each rule. The result is a
`CheckReport` carrying a structured `decision` (`pass`/`warn`/`block`),
a list of `Violation`s with prescriptive next-step text, and metadata about
the inputs that were considered.

The evaluator is deliberately offline, deterministic, and side-effect-free —
no network calls, no model inference, no implicit "best effort" fallbacks. A
malformed lockfile or unsupported rule kind raises `LockfileError` instead of
degrading to a silent pass; an evidence path that escapes the discovered repo
root raises `RepoBoundaryError`.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from cldc._logging import get_logger
from cldc.compiler.policy_compiler import LOCKFILE_FORMAT_VERSION, LOCKFILE_SCHEMA, _compute_source_digest
from cldc.errors import LockfileError, RepoBoundaryError
from cldc.ingest.discovery import LOCKFILE_PATH, discover_policy_repo
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents
from cldc.runtime.events import EMPTY_EXECUTION_INPUTS, load_execution_inputs
from cldc.runtime.report_schema import CHECK_REPORT_FORMAT_VERSION, CHECK_REPORT_SCHEMA

logger = get_logger(__name__)

BLOCKING_MODES = {"block", "fix"}
NON_BLOCKING_MODES = {"observe", "warn"}
ALLOWED_MODES = BLOCKING_MODES | NON_BLOCKING_MODES
ALLOWED_RULE_KINDS = {
    "deny_write",
    "require_read",
    "require_command",
    "forbid_command",
    "couple_change",
    "require_claim",
}


@dataclass(frozen=True)
class Violation:
    """One policy violation with enough context to explain and remediate it."""

    rule_id: str
    kind: str
    mode: str
    message: str
    explanation: str
    recommended_action: str
    matched_paths: list[str]
    matched_commands: list[str]
    matched_claims: list[str]
    required_paths: list[str]
    required_commands: list[str]
    required_claims: list[str]
    source_path: str | None
    source_block_id: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of every violation field."""
        return asdict(self)


@dataclass(frozen=True)
class CheckReport:
    """Versioned outcome of evaluating runtime evidence against compiled policy."""

    ok: bool
    repo_root: str
    lockfile_path: str
    decision: str
    default_mode: str
    summary: str
    next_action: str | None
    inputs: dict[str, list[str]]
    violation_count: int
    blocking_violation_count: int
    violations: list[Violation]

    def to_dict(self) -> dict[str, Any]:
        """Return the versioned JSON-serializable report payload.

        The shape is the normative `policy-report/v1` schema documented in
        `docs/rfcs/CLDC-0002-check-report.md`. Every key is always present;
        absent-by-default values are zero-length lists rather than `None`.
        """
        return {
            "$schema": CHECK_REPORT_SCHEMA,
            "format_version": CHECK_REPORT_FORMAT_VERSION,
            "ok": self.ok,
            "repo_root": self.repo_root,
            "lockfile_path": self.lockfile_path,
            "decision": self.decision,
            "default_mode": self.default_mode,
            "summary": self.summary,
            "next_action": self.next_action,
            "inputs": self.inputs,
            "violation_count": self.violation_count,
            "blocking_violation_count": self.blocking_violation_count,
            "violations": [violation.to_dict() for violation in self.violations],
        }


def _normalize_paths(paths: list[str] | None, *, repo_root: Path) -> list[str]:
    normalized: list[str] = []
    resolved_root = repo_root.resolve()
    for raw in paths or []:
        candidate = raw.strip()
        if not candidate:
            continue

        path_obj = Path(candidate)
        if not path_obj.is_absolute():
            path_obj = resolved_root / path_obj

        resolved_path = path_obj.resolve(strict=False)
        try:
            relative_path = resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise RepoBoundaryError(f"input path {raw!r} resolves outside the discovered repo root {resolved_root}") from exc

        normalized_path = relative_path.as_posix()
        if normalized_path == ".":
            continue
        normalized.append(normalized_path)
    return normalized


def _normalize_commands(commands: list[str] | None) -> list[str]:
    return [command.strip() for command in (commands or []) if command.strip()]


def _matches_any(path: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _matching_paths(paths: list[str], patterns: list[str] | None) -> list[str]:
    return [path for path in paths if _matches_any(path, patterns)]


def _matching_commands(commands: list[str], expected: list[str] | None) -> list[str]:
    if not expected:
        return []
    return [command for command in commands if command in expected]


def _matching_claims(claims: list[str], expected: list[str] | None) -> list[str]:
    if not expected:
        return []
    return [claim for claim in claims if claim in expected]


def _matching_coupled_paths(
    write_paths: list[str],
    *,
    triggered_paths: list[str],
    required_patterns: list[str] | None,
) -> list[str]:
    if not required_patterns:
        return []
    triggered_path_set = set(triggered_paths)
    return [path for path in write_paths if path not in triggered_path_set and _matches_any(path, required_patterns)]


def _load_lockfile(repo_root: Path) -> dict[str, Any]:
    lockfile = repo_root / LOCKFILE_PATH
    if not lockfile.exists():
        raise FileNotFoundError(f"compiled lockfile not found at {LOCKFILE_PATH}; run `cldc compile` before `cldc check`")

    try:
        payload = json.loads(lockfile.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise LockfileError(f"compiled lockfile is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LockfileError("compiled lockfile must contain a JSON object at the top level")

    if payload.get("$schema") != LOCKFILE_SCHEMA:
        raise LockfileError("compiled lockfile schema does not match this checker; re-run `cldc compile` to refresh it")
    if payload.get("format_version") != LOCKFILE_FORMAT_VERSION:
        raise LockfileError("compiled lockfile format_version does not match this checker; re-run `cldc compile` to refresh it")
    if payload.get("repo_root") != str(repo_root):
        raise LockfileError("compiled lockfile repo_root does not match the discovered repository root; re-run `cldc compile`")

    default_mode = payload.get("default_mode")
    if default_mode not in ALLOWED_MODES:
        raise LockfileError(f"compiled lockfile has invalid default_mode: {default_mode!r}")

    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise LockfileError("compiled lockfile must contain a 'rules' list")

    rule_count = payload.get("rule_count")
    if not isinstance(rule_count, int):
        raise LockfileError("compiled lockfile must contain an integer 'rule_count'")
    if rule_count != len(rules):
        raise LockfileError("compiled lockfile rule_count does not match the embedded rules; re-run `cldc compile`")

    logger.debug("loaded lockfile with %d rules from %s", len(rules), lockfile)
    return payload


def _validate_lockfile_freshness(repo_root: Path, payload: dict[str, Any]) -> None:
    bundle = load_policy_sources(repo_root)
    parsed = parse_rule_documents(bundle)
    lockfile = repo_root / LOCKFILE_PATH

    repo_local_mtimes: list[float] = []
    for source in bundle.sources:
        # Preset sources live inside the installed cldc package, not the
        # repo — their content is covered by the source_digest check below,
        # so they are skipped here.
        if source.path.startswith("preset:"):
            continue
        repo_local_mtimes.append((repo_root / source.path).stat().st_mtime)
    if repo_local_mtimes and lockfile.stat().st_mtime < max(repo_local_mtimes):
        raise LockfileError("compiled lockfile appears stale relative to the current policy sources; re-run `cldc compile`")

    if payload["default_mode"] != parsed.default_mode:
        raise LockfileError("compiled lockfile default_mode does not match the current policy sources; re-run `cldc compile`")
    if payload["rule_count"] != len(parsed.rules):
        raise LockfileError("compiled lockfile rule_count does not match the current policy sources; re-run `cldc compile`")

    current_source_digest = _compute_source_digest(bundle)
    lockfile_source_digest = payload.get("source_digest")
    if not isinstance(lockfile_source_digest, str) or len(lockfile_source_digest) != 64:
        raise LockfileError("compiled lockfile source_digest is missing or invalid; re-run `cldc compile` to refresh it")
    if lockfile_source_digest != current_source_digest:
        raise LockfileError("compiled lockfile source_digest does not match the current policy sources; re-run `cldc compile`")


def _effective_mode(rule: dict[str, Any], default_mode: str) -> str:
    mode = rule.get("mode") or default_mode
    if mode not in ALLOWED_MODES:
        raise LockfileError(f"rule '{rule.get('id', '<unknown>')}' has invalid mode: {mode!r}")
    return mode


def _join_for_humans(values: list[str]) -> str:
    if not values:
        return "<none>"
    if len(values) == 1:
        return values[0]
    return ", ".join(values)


def _explain_violation(
    rule: dict[str, Any],
    *,
    matched_paths: list[str],
    matched_commands: list[str],
    required_paths: list[str],
    required_commands: list[str],
    required_claims: list[str],
) -> tuple[str, str]:
    rule_id = str(rule.get("id", "<unknown>"))
    kind = str(rule.get("kind", "<unknown>"))
    path_list = _join_for_humans(matched_paths)
    command_list = _join_for_humans(matched_commands)
    required_path_list = _join_for_humans(required_paths)
    required_command_list = _join_for_humans(required_commands)
    required_claim_list = _join_for_humans(required_claims)

    if kind == "deny_write":
        return (
            f"Write activity {path_list} matched deny_write rule '{rule_id}'.",
            f"Avoid writing paths matching {required_path_list if required_paths else _join_for_humans(list(rule.get('paths') or []))}.",
        )
    if kind == "require_read":
        return (
            f"Write activity {path_list} triggered require_read rule '{rule_id}', but no required read matched {required_path_list}.",
            f"Read at least one path matching {required_path_list} before modifying {path_list}.",
        )
    if kind == "require_command":
        return (
            f"Write activity {path_list} triggered require_command rule '{rule_id}', but no required command matched {required_command_list}.",
            f"Run one of the required commands before finishing: {required_command_list}.",
        )
    if kind == "forbid_command":
        forbidden_list = _join_for_humans(list(rule.get("commands") or []))
        if matched_paths:
            return (
                f"Forbidden command(s) {command_list} ran while writing {path_list}, matching forbid_command rule '{rule_id}'.",
                f"Do not run {forbidden_list} when touching paths matching {_join_for_humans(list(rule.get('when_paths') or []))}; "
                "revert or replace the invocation with an allowed alternative.",
            )
        return (
            f"Forbidden command(s) {command_list} ran, matching forbid_command rule '{rule_id}'.",
            f"Do not run {forbidden_list} in this repository; revert or replace the invocation with an allowed alternative.",
        )
    if kind == "couple_change":
        return (
            f"Write activity {path_list} triggered couple_change rule '{rule_id}', but no coupled change matched {required_path_list}.",
            f"Update at least one path matching {required_path_list} alongside {path_list}.",
        )
    if kind == "require_claim":
        return (
            f"Write activity {path_list} triggered require_claim rule '{rule_id}', but no required claim matched {required_claim_list}.",
            f"Record one of the required claims before finishing: {required_claim_list}.",
        )
    return (
        f"Rule '{rule_id}' triggered for paths {path_list} and commands {command_list}.",
        "Inspect the matched rule and input evidence, then rerun the policy check.",
    )


def _build_violation(
    rule: dict[str, Any],
    *,
    default_mode: str,
    matched_paths: list[str] | None = None,
    matched_commands: list[str] | None = None,
    matched_claims: list[str] | None = None,
    required_paths: list[str] | None = None,
    required_commands: list[str] | None = None,
    required_claims: list[str] | None = None,
) -> Violation:
    normalized_matched_paths = list(matched_paths or [])
    normalized_matched_commands = list(matched_commands or [])
    normalized_matched_claims = list(matched_claims or [])
    normalized_required_paths = list(required_paths or [])
    normalized_required_commands = list(required_commands or [])
    normalized_required_claims = list(required_claims or [])
    explanation, recommended_action = _explain_violation(
        rule,
        matched_paths=normalized_matched_paths,
        matched_commands=normalized_matched_commands,
        required_paths=normalized_required_paths,
        required_commands=normalized_required_commands,
        required_claims=normalized_required_claims,
    )
    rule_id = str(rule.get("id", "<unknown>"))
    logger.debug("rule %s fired: %d matched paths", rule_id, len(normalized_matched_paths))
    return Violation(
        rule_id=rule_id,
        kind=str(rule.get("kind", "<unknown>")),
        mode=_effective_mode(rule, default_mode),
        message=str(rule.get("message", "")),
        explanation=explanation,
        recommended_action=recommended_action,
        matched_paths=normalized_matched_paths,
        matched_commands=normalized_matched_commands,
        matched_claims=normalized_matched_claims,
        required_paths=normalized_required_paths,
        required_commands=normalized_required_commands,
        required_claims=normalized_required_claims,
        source_path=rule.get("source_path"),
        source_block_id=rule.get("source_block_id"),
    )


def _summarize_report(*, decision: str, violation_count: int, blocking_violation_count: int) -> str:
    if violation_count == 0:
        return "Policy check passed with no violations."
    if decision == "block":
        return f"Policy check found {violation_count} violation(s), including {blocking_violation_count} blocking violation(s)."
    return f"Policy check found {violation_count} non-blocking violation(s)."


def _next_action_for_violations(violations: list[Violation]) -> str | None:
    if not violations:
        return None
    for violation in violations:
        if violation.mode in BLOCKING_MODES:
            return violation.recommended_action
    return violations[0].recommended_action


def _evaluate_rule(
    rule: dict[str, Any],
    *,
    default_mode: str,
    read_paths: list[str],
    write_paths: list[str],
    commands: list[str],
    claims: list[str],
) -> Violation | None:
    kind = rule.get("kind")
    if kind not in ALLOWED_RULE_KINDS:
        raise LockfileError(f"compiled lockfile contains unsupported rule kind: {kind!r}")

    if kind == "deny_write":
        matched_paths = _matching_paths(write_paths, rule.get("paths"))
        if matched_paths:
            return _build_violation(rule, default_mode=default_mode, matched_paths=matched_paths)
        return None

    if kind == "require_read":
        triggered_paths = _matching_paths(write_paths, rule.get("paths"))
        if not triggered_paths:
            return None
        matched_reads = _matching_paths(read_paths, rule.get("before_paths"))
        if matched_reads:
            return None
        return _build_violation(
            rule,
            default_mode=default_mode,
            matched_paths=triggered_paths,
            required_paths=list(rule.get("before_paths") or []),
        )

    if kind == "couple_change":
        triggered_paths = _matching_paths(write_paths, rule.get("paths"))
        if not triggered_paths:
            return None
        matched_coupled_paths = _matching_coupled_paths(
            write_paths,
            triggered_paths=triggered_paths,
            required_patterns=rule.get("when_paths"),
        )
        if matched_coupled_paths:
            return None
        return _build_violation(
            rule,
            default_mode=default_mode,
            matched_paths=triggered_paths,
            required_paths=list(rule.get("when_paths") or []),
        )

    if kind == "require_claim":
        triggered_paths = _matching_paths(write_paths, rule.get("when_paths"))
        if not triggered_paths:
            return None
        matched_claims = _matching_claims(claims, rule.get("claims"))
        if matched_claims:
            return None
        return _build_violation(
            rule,
            default_mode=default_mode,
            matched_paths=triggered_paths,
            required_claims=list(rule.get("claims") or []),
        )

    if kind == "forbid_command":
        forbidden_commands = _matching_commands(commands, rule.get("commands"))
        if not forbidden_commands:
            return None
        when_paths = rule.get("when_paths")
        if when_paths:
            triggered_paths = _matching_paths(write_paths, when_paths)
            if not triggered_paths:
                return None
        else:
            triggered_paths = []
        return _build_violation(
            rule,
            default_mode=default_mode,
            matched_paths=triggered_paths,
            matched_commands=forbidden_commands,
        )

    triggered_paths = _matching_paths(write_paths, rule.get("when_paths"))
    if not triggered_paths:
        return None
    matched_commands = _matching_commands(commands, rule.get("commands"))
    if matched_commands:
        return None
    return _build_violation(
        rule,
        default_mode=default_mode,
        matched_paths=triggered_paths,
        required_commands=list(rule.get("commands") or []),
    )


def check_repo_policy(
    repo_root: Path | str,
    *,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
    commands: list[str] | None = None,
    claims: list[str] | None = None,
    event_payload: dict[str, Any] | None = None,
) -> CheckReport:
    """Evaluate runtime evidence against the compiled policy lockfile for a repo."""

    discovery = discover_policy_repo(repo_root)
    if not discovery.discovered:
        raise FileNotFoundError(discovery.warnings[0])

    root = Path(discovery.repo_root)
    payload = _load_lockfile(root)
    _validate_lockfile_freshness(root, payload)
    default_mode = payload["default_mode"]

    event_inputs = load_execution_inputs(event_payload) if event_payload is not None else EMPTY_EXECUTION_INPUTS
    normalized_reads = _normalize_paths([*(read_paths or []), *event_inputs.read_paths], repo_root=root)
    normalized_writes = _normalize_paths([*(write_paths or []), *event_inputs.write_paths], repo_root=root)
    normalized_commands = _normalize_commands([*(commands or []), *event_inputs.commands])
    normalized_claims = _normalize_commands([*(claims or []), *event_inputs.claims])

    violations: list[Violation] = []
    for rule in payload["rules"]:
        if not isinstance(rule, dict):
            raise LockfileError("compiled lockfile contains a non-object rule entry")
        violation = _evaluate_rule(
            rule,
            default_mode=default_mode,
            read_paths=normalized_reads,
            write_paths=normalized_writes,
            commands=normalized_commands,
            claims=normalized_claims,
        )
        if violation:
            violations.append(violation)

    blocking_violation_count = sum(1 for violation in violations if violation.mode in BLOCKING_MODES)
    if blocking_violation_count:
        decision = "block"
        ok = False
    elif violations:
        decision = "warn"
        ok = True
    else:
        decision = "pass"
        ok = True

    violation_count = len(violations)
    logger.debug(
        "check complete: decision=%s violations=%d blocking=%d",
        decision,
        violation_count,
        blocking_violation_count,
    )
    return CheckReport(
        ok=ok,
        repo_root=str(root),
        lockfile_path=LOCKFILE_PATH,
        decision=decision,
        default_mode=default_mode,
        summary=_summarize_report(
            decision=decision,
            violation_count=violation_count,
            blocking_violation_count=blocking_violation_count,
        ),
        next_action=_next_action_for_violations(violations),
        inputs={
            "read_paths": normalized_reads,
            "write_paths": normalized_writes,
            "commands": normalized_commands,
            "claims": normalized_claims,
        },
        violation_count=violation_count,
        blocking_violation_count=blocking_violation_count,
        violations=violations,
    )
