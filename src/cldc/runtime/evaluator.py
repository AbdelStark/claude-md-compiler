from __future__ import annotations

from dataclasses import asdict, dataclass
import fnmatch
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from cldc.compiler.policy_compiler import LOCKFILE_FORMAT_VERSION, LOCKFILE_SCHEMA
from cldc.ingest.discovery import LOCKFILE_PATH, discover_policy_repo
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents
from cldc.runtime.events import EMPTY_EXECUTION_INPUTS, load_execution_inputs

BLOCKING_MODES = {"block", "fix"}
NON_BLOCKING_MODES = {"observe", "warn"}
ALLOWED_MODES = BLOCKING_MODES | NON_BLOCKING_MODES
ALLOWED_RULE_KINDS = {"deny_write", "require_read", "require_command"}


@dataclass(frozen=True)
class Violation:
    rule_id: str
    kind: str
    mode: str
    message: str
    matched_paths: list[str]
    matched_commands: list[str]
    required_paths: list[str]
    required_commands: list[str]
    source_path: str | None
    source_block_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckReport:
    ok: bool
    repo_root: str
    lockfile_path: str
    decision: str
    default_mode: str
    inputs: dict[str, list[str]]
    violation_count: int
    blocking_violation_count: int
    violations: list[Violation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo_root": self.repo_root,
            "lockfile_path": self.lockfile_path,
            "decision": self.decision,
            "default_mode": self.default_mode,
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
            raise ValueError(
                f"input path {raw!r} resolves outside the discovered repo root {resolved_root}"
            ) from exc

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


def _load_lockfile(repo_root: Path) -> dict[str, Any]:
    lockfile = repo_root / LOCKFILE_PATH
    if not lockfile.exists():
        raise FileNotFoundError(
            f"compiled lockfile not found at {LOCKFILE_PATH}; run `cldc compile` before `cldc check`"
        )

    try:
        payload = json.loads(lockfile.read_text())
    except JSONDecodeError as exc:
        raise ValueError(f"compiled lockfile is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("compiled lockfile must contain a JSON object at the top level")

    if payload.get("$schema") != LOCKFILE_SCHEMA:
        raise ValueError(
            "compiled lockfile schema does not match this checker; re-run `cldc compile` to refresh it"
        )
    if payload.get("format_version") != LOCKFILE_FORMAT_VERSION:
        raise ValueError(
            "compiled lockfile format_version does not match this checker; re-run `cldc compile` to refresh it"
        )
    if payload.get("repo_root") != str(repo_root):
        raise ValueError(
            "compiled lockfile repo_root does not match the discovered repository root; re-run `cldc compile`"
        )

    default_mode = payload.get("default_mode")
    if default_mode not in ALLOWED_MODES:
        raise ValueError(f"compiled lockfile has invalid default_mode: {default_mode!r}")

    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("compiled lockfile must contain a 'rules' list")

    rule_count = payload.get("rule_count")
    if not isinstance(rule_count, int):
        raise ValueError("compiled lockfile must contain an integer 'rule_count'")
    if rule_count != len(rules):
        raise ValueError(
            "compiled lockfile rule_count does not match the embedded rules; re-run `cldc compile`"
        )

    return payload


def _validate_lockfile_freshness(repo_root: Path, payload: dict[str, Any]) -> None:
    bundle = load_policy_sources(repo_root)
    parsed = parse_rule_documents(bundle)
    lockfile = repo_root / LOCKFILE_PATH

    newest_source_mtime = max((repo_root / source.path).stat().st_mtime for source in bundle.sources)
    if lockfile.stat().st_mtime < newest_source_mtime:
        raise ValueError(
            "compiled lockfile appears stale relative to the current policy sources; re-run `cldc compile`"
        )

    if payload["default_mode"] != parsed.default_mode:
        raise ValueError(
            "compiled lockfile default_mode does not match the current policy sources; re-run `cldc compile`"
        )
    if payload["rule_count"] != len(parsed.rules):
        raise ValueError(
            "compiled lockfile rule_count does not match the current policy sources; re-run `cldc compile`"
        )


def _effective_mode(rule: dict[str, Any], default_mode: str) -> str:
    mode = rule.get("mode") or default_mode
    if mode not in ALLOWED_MODES:
        raise ValueError(f"rule '{rule.get('id', '<unknown>')}' has invalid mode: {mode!r}")
    return mode


def _build_violation(
    rule: dict[str, Any],
    *,
    default_mode: str,
    matched_paths: list[str] | None = None,
    matched_commands: list[str] | None = None,
    required_paths: list[str] | None = None,
    required_commands: list[str] | None = None,
) -> Violation:
    return Violation(
        rule_id=str(rule.get("id", "<unknown>")),
        kind=str(rule.get("kind", "<unknown>")),
        mode=_effective_mode(rule, default_mode),
        message=str(rule.get("message", "")),
        matched_paths=list(matched_paths or []),
        matched_commands=list(matched_commands or []),
        required_paths=list(required_paths or []),
        required_commands=list(required_commands or []),
        source_path=rule.get("source_path"),
        source_block_id=rule.get("source_block_id"),
    )


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
        return None

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
    event_payload: dict[str, Any] | None = None,
) -> CheckReport:
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
    normalized_claims = _normalize_commands(event_inputs.claims)

    violations: list[Violation] = []
    for rule in payload["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("compiled lockfile contains a non-object rule entry")
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

    return CheckReport(
        ok=ok,
        repo_root=str(root),
        lockfile_path=LOCKFILE_PATH,
        decision=decision,
        default_mode=default_mode,
        inputs={
            "read_paths": normalized_reads,
            "write_paths": normalized_writes,
            "commands": normalized_commands,
            "claims": normalized_claims,
        },
        violation_count=len(violations),
        blocking_violation_count=blocking_violation_count,
        violations=violations,
    )
