from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from cldc import __version__
from cldc._logging import get_logger
from cldc.errors import CldcError
from cldc.ingest.source_loader import SOURCE_PRECEDENCE, load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents

logger = get_logger(__name__)

LOCKFILE_FORMAT_VERSION = "1"
LOCKFILE_SCHEMA = "https://cldc.dev/schemas/policy-lock/v1"


@dataclass(frozen=True)
class CompiledPolicy:
    """Summary of a successful compile run and the artifact it produced."""

    repo_root: str
    lockfile_path: str
    compiler_version: str
    format_version: str
    source_digest: str
    default_mode: str
    rule_count: int
    source_count: int
    source_paths: list[str]
    warnings: list[str]
    discovery: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of every field."""
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    """Health report for source discovery, parsing, and lockfile state."""

    repo_root: str
    discovered: bool
    source_count: int
    rule_count: int
    default_mode: str | None
    source_digest: str | None
    lockfile_path: str
    lockfile_exists: bool
    lockfile_schema: str | None
    lockfile_format_version: str | None
    lockfile_source_digest: str | None
    warnings: list[str]
    errors: list[str]
    next_action: str | None
    discovery: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of every field."""
        return asdict(self)


def _compute_source_digest(bundle) -> str:
    canonical_sources = {
        "source_precedence": SOURCE_PRECEDENCE,
        "sources": [source.to_dict() for source in bundle.sources],
    }
    canonical_json = json.dumps(canonical_sources, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _build_lock_payload(repo_root: Path, bundle, parsed) -> dict[str, Any]:
    source_digest = _compute_source_digest(bundle)
    return {
        "$schema": LOCKFILE_SCHEMA,
        "compiler_version": __version__,
        "format_version": LOCKFILE_FORMAT_VERSION,
        "repo_root": str(repo_root),
        "default_mode": parsed.default_mode,
        "rule_count": len(parsed.rules),
        "source_count": len(bundle.sources),
        "source_digest": source_digest,
        "source_precedence": SOURCE_PRECEDENCE,
        "discovery": bundle.discovery.to_dict(),
        "sources": [source.to_dict() for source in bundle.sources],
        "rules": [rule.to_dict() for rule in parsed.rules],
    }


def _compiled_discovery(discovery: dict[str, Any]) -> dict[str, Any]:
    compiled_discovery = dict(discovery)
    compiled_discovery["lockfile_path"] = ".claude/policy.lock.json"
    compiled_discovery["warnings"] = [
        warning
        for warning in compiled_discovery.get("warnings", [])
        if warning != "compiled lockfile not found at .claude/policy.lock.json"
    ]
    return compiled_discovery


def compile_repo_policy(repo_root: Path | str) -> CompiledPolicy:
    """Compile policy sources into a deterministic lockfile under `.claude/`."""

    bundle = load_policy_sources(repo_root)
    parsed = parse_rule_documents(bundle)
    root = Path(bundle.repo_root)
    payload = _build_lock_payload(root, bundle, parsed)

    lock_dir = root / ".claude"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "policy.lock.json"
    lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    discovery = _compiled_discovery(bundle.discovery.to_dict())

    compiled = CompiledPolicy(
        repo_root=str(root),
        lockfile_path=".claude/policy.lock.json",
        compiler_version=__version__,
        format_version=LOCKFILE_FORMAT_VERSION,
        source_digest=payload["source_digest"],
        default_mode=parsed.default_mode,
        rule_count=len(parsed.rules),
        source_count=len(bundle.sources),
        source_paths=[source.path for source in bundle.sources],
        warnings=list(discovery["warnings"]),
        discovery=discovery,
    )
    logger.debug(
        "compiled %d rules from %d sources into %s",
        compiled.rule_count,
        compiled.source_count,
        compiled.lockfile_path,
    )
    return compiled


def _safe_resolve(path: Path | str) -> str:
    # Path.resolve(strict=False) — the default — never raises for missing
    # paths, so this is just a thin alias kept for readability.
    return str(Path(path).resolve())


def _empty_doctor_report(repo_root: Path | str, errors: list[str]) -> DoctorReport:
    """Build a DoctorReport that represents a failure before discovery completed."""
    return DoctorReport(
        repo_root=_safe_resolve(repo_root),
        discovered=False,
        source_count=0,
        rule_count=0,
        default_mode=None,
        source_digest=None,
        lockfile_path=".claude/policy.lock.json",
        lockfile_exists=False,
        lockfile_schema=None,
        lockfile_format_version=None,
        lockfile_source_digest=None,
        warnings=[],
        errors=errors,
        next_action=_recommend_next_action(errors, []),
        discovery={},
    )


def _validate_existing_lockfile(
    lockfile: Path,
    *,
    repo_root: Path,
    expected_rule_count: int,
    expected_source_digest: str,
    errors: list[str],
    warnings: list[str],
) -> tuple[str | None, str | None, str | None]:
    try:
        payload = json.loads(lockfile.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        errors.append(f"lockfile is not valid JSON: {exc}")
        return None, None, None

    if not isinstance(payload, dict):
        errors.append("lockfile must contain a JSON object at the top level")
        return None, None, None

    lockfile_schema = payload.get("$schema")
    lockfile_format_version = payload.get("format_version")
    lockfile_source_digest = payload.get("source_digest")

    if lockfile_schema != LOCKFILE_SCHEMA:
        warnings.append("lockfile schema does not match compiler expectation; re-run `cldc compile` to refresh it")
    if lockfile_format_version != LOCKFILE_FORMAT_VERSION:
        warnings.append("lockfile format_version does not match compiler expectation; re-run `cldc compile` to refresh it")
    if payload.get("repo_root") != str(repo_root):
        warnings.append("lockfile repo_root does not match the discovered repository root")
    if payload.get("rule_count") != expected_rule_count:
        warnings.append("lockfile rule_count does not match the currently parsed policy sources")
    if not isinstance(lockfile_source_digest, str) or len(lockfile_source_digest) != 64:
        warnings.append("lockfile source_digest is missing or invalid; re-run `cldc compile` to refresh it")
    elif lockfile_source_digest != expected_source_digest:
        warnings.append("lockfile source_digest does not match the current policy sources")

    return (
        lockfile_schema if isinstance(lockfile_schema, str) else None,
        lockfile_format_version if isinstance(lockfile_format_version, str) else None,
        lockfile_source_digest if isinstance(lockfile_source_digest, str) else None,
    )


def _recommend_next_action(errors: list[str], warnings: list[str]) -> str | None:
    if errors:
        return "Fix the reported policy or lockfile errors, then rerun `cldc doctor` and `cldc compile`."
    if any("stale" in warning or "does not match" in warning for warning in warnings):
        return "Re-run `cldc compile` to refresh the lockfile, then commit the updated artifact."
    if any("compiled lockfile not found" in warning for warning in warnings):
        return "Run `cldc compile` to generate the initial lockfile artifact."
    if any("no policy fragments" in warning for warning in warnings):
        return "Add policy fragments under `policies/` or inline `cldc` blocks to increase enforcement coverage."
    return None


def doctor_repo_policy(repo_root: Path | str) -> DoctorReport:
    """Inspect policy discovery, parsing health, and lockfile freshness."""

    errors: list[str] = []
    warnings: list[str] = []

    try:
        bundle = load_policy_sources(repo_root)
    except (FileNotFoundError, CldcError) as exc:
        # Discovery, IO, or source-loading failure. Report the raw message
        # via DoctorReport.errors rather than propagating the exception so
        # `cldc doctor` stays useful even on a broken repo. Non-cldc and
        # non-IO exceptions (programming errors) are intentionally left to
        # propagate so they surface in tests and bug reports.
        return _empty_doctor_report(repo_root, [str(exc)])

    warnings.extend(bundle.discovery.warnings)
    root = Path(bundle.repo_root)
    lockfile = root / ".claude" / "policy.lock.json"
    lockfile_schema: str | None = None
    lockfile_format_version: str | None = None
    lockfile_source_digest: str | None = None
    source_digest: str | None = None

    try:
        parsed = parse_rule_documents(bundle)
        default_mode = parsed.default_mode
        rule_count = len(parsed.rules)
        source_digest = _compute_source_digest(bundle)
    except CldcError as exc:
        # Typed rule-validation or policy-source errors are expected on a
        # drifted repo. Programmer errors (e.g. AttributeError) are left to
        # propagate so the CLI's error handler surfaces a real traceback.
        errors.append(str(exc))
        default_mode = None
        rule_count = 0
    else:
        if lockfile.exists():
            lockfile_schema, lockfile_format_version, lockfile_source_digest = _validate_existing_lockfile(
                lockfile,
                repo_root=root,
                expected_rule_count=rule_count,
                expected_source_digest=source_digest,
                errors=errors,
                warnings=warnings,
            )

    if not bundle.sources:
        warnings.append("no sources were loaded")
    if lockfile.exists() and bundle.sources:
        # Preset sources live inside the installed cldc package, not the
        # repo — their content is covered by the source_digest check, so
        # they are skipped here to avoid FileNotFoundError on `preset:*`
        # paths.
        repo_local_mtimes = [(root / source.path).stat().st_mtime for source in bundle.sources if not source.path.startswith("preset:")]
        if repo_local_mtimes and lockfile.stat().st_mtime < max(repo_local_mtimes):
            warnings.append("lockfile appears stale relative to policy sources")

    next_action = _recommend_next_action(errors, warnings)
    report = DoctorReport(
        repo_root=str(root),
        discovered=True,
        source_count=len(bundle.sources),
        rule_count=rule_count,
        default_mode=default_mode,
        source_digest=source_digest,
        lockfile_path=".claude/policy.lock.json",
        lockfile_exists=lockfile.exists(),
        lockfile_schema=lockfile_schema,
        lockfile_format_version=lockfile_format_version,
        lockfile_source_digest=lockfile_source_digest,
        warnings=warnings,
        errors=errors,
        next_action=next_action,
        discovery=bundle.discovery.to_dict(),
    )
    logger.debug(
        "doctor report: %d errors, %d warnings, next_action=%s",
        len(report.errors),
        len(report.warnings),
        report.next_action,
    )
    return report
