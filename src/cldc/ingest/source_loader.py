from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

import yaml


@dataclass(frozen=True)
class PolicySource:
    kind: str
    path: str
    content: str
    block_id: str | None = None
    line_start: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceBundle:
    repo_root: str
    sources: list[PolicySource]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "sources": [source.to_dict() for source in self.sources],
        }


def _extract_inline_blocks(claude_path: Path, text: str) -> list[PolicySource]:
    pattern = re.compile(r"```cldc\s*\r?\n(.*?)\r?\n```", re.DOTALL)
    sources: list[PolicySource] = []
    for match in pattern.finditer(text):
        line_start = text[: match.start()].count("\n") + 1
        sources.append(
            PolicySource(
                kind="inline_block",
                path=claude_path.name,
                content=match.group(1).strip() + "\n",
                block_id=f"{claude_path.name}:{line_start}",
                line_start=line_start,
            )
        )
    return sources


def _load_include_patterns(config_text: str) -> list[str]:
    config_data = yaml.safe_load(config_text) or {}
    include = config_data.get("include", [])
    if include is None:
        return []
    if not isinstance(include, list) or any(not isinstance(item, str) for item in include):
        raise ValueError("include must be a list of glob strings")
    return include


def load_policy_sources(repo_root: Path | str) -> SourceBundle:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(root)

    sources: list[PolicySource] = []

    claude_path = root / "CLAUDE.md"
    if claude_path.exists():
        claude_text = claude_path.read_text()
        sources.append(PolicySource(kind="claude_md", path="CLAUDE.md", content=claude_text))
        sources.extend(_extract_inline_blocks(claude_path, claude_text))

    include_patterns = ["policies/*.yml", "policies/*.yaml"]
    config_path = root / ".claude-compiler.yaml"
    if config_path.exists():
        config_text = config_path.read_text()
        sources.append(
            PolicySource(kind="compiler_config", path=".claude-compiler.yaml", content=config_text)
        )
        include_patterns.extend(_load_include_patterns(config_text))

    seen_policy_paths: set[str] = set()
    for pattern_name in sorted(set(include_patterns)):
        for policy_path in sorted(root.glob(pattern_name)):
            if policy_path.is_file():
                rel = policy_path.relative_to(root).as_posix()
                if rel in seen_policy_paths:
                    continue
                seen_policy_paths.add(rel)
                sources.append(
                    PolicySource(kind="policy_file", path=rel, content=policy_path.read_text())
                )

    return SourceBundle(repo_root=str(root), sources=sources)
