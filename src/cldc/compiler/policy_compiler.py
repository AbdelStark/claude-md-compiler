from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from cldc import __version__
from cldc.ingest.source_loader import load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents

LOCKFILE_FORMAT_VERSION = "1"


@dataclass(frozen=True)
class CompiledPolicy:
    repo_root: str
    lockfile_path: str
    compiler_version: str
    format_version: str
    rule_count: int


def compile_repo_policy(repo_root: Path | str) -> CompiledPolicy:
    root = Path(repo_root)
    bundle = load_policy_sources(root)
    parsed = parse_rule_documents(bundle)

    payload = {
        "compiler_version": __version__,
        "format_version": LOCKFILE_FORMAT_VERSION,
        "repo_root": str(root),
        "default_mode": parsed.default_mode,
        "rule_count": len(parsed.rules),
        "source_precedence": [source.kind for source in bundle.sources],
        "sources": [source.to_dict() for source in bundle.sources],
        "rules": [rule.to_dict() for rule in parsed.rules],
    }

    lock_dir = root / ".claude"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "policy.lock.json"
    lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + chr(10))

    return CompiledPolicy(
        repo_root=str(root),
        lockfile_path=".claude/policy.lock.json",
        compiler_version=__version__,
        format_version=LOCKFILE_FORMAT_VERSION,
        rule_count=len(parsed.rules),
    )
