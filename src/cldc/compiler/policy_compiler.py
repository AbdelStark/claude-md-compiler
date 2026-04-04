from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from cldc import __version__
from cldc.ingest.source_loader import SOURCE_PRECEDENCE, load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents

LOCKFILE_FORMAT_VERSION = "1"
LOCKFILE_SCHEMA = "https://cldc.dev/schemas/policy-lock/v1"


@dataclass(frozen=True)
class CompiledPolicy:
    repo_root: str
    lockfile_path: str
    compiler_version: str
    format_version: str
    rule_count: int
    source_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    repo_root: str
    discovered: bool
    source_count: int
    rule_count: int
    default_mode: str | None
    lockfile_path: str
    lockfile_exists: bool
    warnings: list[str]
    errors: list[str]
    discovery: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_lock_payload(repo_root: Path, bundle, parsed) -> dict[str, Any]:
    return {
        "$schema": LOCKFILE_SCHEMA,
        "compiler_version": __version__,
        "format_version": LOCKFILE_FORMAT_VERSION,
        "repo_root": str(repo_root),
        "default_mode": parsed.default_mode,
        "rule_count": len(parsed.rules),
        "source_count": len(bundle.sources),
        "source_precedence": SOURCE_PRECEDENCE,
        "discovery": bundle.discovery.to_dict(),
        "sources": [source.to_dict() for source in bundle.sources],
        "rules": [rule.to_dict() for rule in parsed.rules],
    }


def compile_repo_policy(repo_root: Path | str) -> CompiledPolicy:
    bundle = load_policy_sources(repo_root)
    parsed = parse_rule_documents(bundle)
    root = Path(bundle.repo_root)
    payload = _build_lock_payload(root, bundle, parsed)

    lock_dir = root / ".claude"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "policy.lock.json"
    lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    return CompiledPolicy(
        repo_root=str(root),
        lockfile_path=".claude/policy.lock.json",
        compiler_version=__version__,
        format_version=LOCKFILE_FORMAT_VERSION,
        rule_count=len(parsed.rules),
        source_count=len(bundle.sources),
    )


def doctor_repo_policy(repo_root: Path | str) -> DoctorReport:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        bundle = load_policy_sources(repo_root)
    except FileNotFoundError as exc:
        return DoctorReport(
            repo_root=str(Path(repo_root).resolve()),
            discovered=False,
            source_count=0,
            rule_count=0,
            default_mode=None,
            lockfile_path=".claude/policy.lock.json",
            lockfile_exists=False,
            warnings=[],
            errors=[str(exc)],
            discovery={},
        )
    except Exception as exc:
        return DoctorReport(
            repo_root=str(Path(repo_root).resolve()),
            discovered=False,
            source_count=0,
            rule_count=0,
            default_mode=None,
            lockfile_path=".claude/policy.lock.json",
            lockfile_exists=False,
            warnings=[],
            errors=[str(exc)],
            discovery={},
        )

    warnings.extend(bundle.discovery.warnings)
    root = Path(bundle.repo_root)
    lockfile = root / ".claude" / "policy.lock.json"

    try:
        parsed = parse_rule_documents(bundle)
        default_mode = parsed.default_mode
        rule_count = len(parsed.rules)
    except Exception as exc:
        errors.append(str(exc))
        default_mode = None
        rule_count = 0

    if not bundle.sources:
        warnings.append("no sources were loaded")
    if lockfile.exists() and bundle.sources:
        newest_source_mtime = max((root / source.path).stat().st_mtime for source in bundle.sources)
        if lockfile.stat().st_mtime < newest_source_mtime:
            warnings.append("lockfile appears stale relative to policy sources")

    return DoctorReport(
        repo_root=str(root),
        discovered=True,
        source_count=len(bundle.sources),
        rule_count=rule_count,
        default_mode=default_mode,
        lockfile_path=".claude/policy.lock.json",
        lockfile_exists=lockfile.exists(),
        warnings=warnings,
        errors=errors,
        discovery=bundle.discovery.to_dict(),
    )
