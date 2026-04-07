from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from pathlib import Path
from pathlib import PurePosixPath

import yaml

from cldc._logging import get_logger
from cldc.ingest.discovery import DEFAULT_POLICY_GLOBS, DiscoveryResult, discover_policy_repo
from cldc.presets import PRESET_SOURCE_KIND, PresetNotFoundError, load_preset, preset_path

logger = get_logger(__name__)

SOURCE_PRECEDENCE = ["claude_md", "inline_block", "compiler_config", PRESET_SOURCE_KIND, "policy_file"]


@dataclass(frozen=True)
class PolicySource:
    """One canonical policy input with preserved provenance."""

    kind: str
    path: str
    content: str
    block_id: str | None = None
    line_start: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceBundle:
    """The ordered set of policy sources discovered for a repository."""

    repo_root: str
    sources: list[PolicySource]
    discovery: DiscoveryResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "discovery": self.discovery.to_dict(),
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


def _load_yaml_document(raw: str, context: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid yaml in {context}: {exc}") from exc
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ValueError(f"expected a YAML mapping in {context}")
    return document


def _load_include_patterns(config_text: str, context: str) -> list[str]:
    config_data = _load_yaml_document(config_text, context)
    include = config_data.get("include", [])
    if include is None:
        return []
    if not isinstance(include, list):
        raise ValueError("include must be a list of glob strings")
    patterns: list[str] = []
    for index, item in enumerate(include):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"include[{index}] must be a non-empty glob string")
        normalized = item.strip()
        candidate = PurePosixPath(normalized.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("include patterns must stay within the repo root")
        patterns.append(normalized)
    return patterns


def _load_preset_names(config_text: str, context: str) -> list[str]:
    config_data = _load_yaml_document(config_text, context)
    extends = config_data.get("extends")
    if extends is None:
        return []
    if not isinstance(extends, list):
        raise ValueError("extends must be a list of preset name strings")
    names: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(extends):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"extends[{index}] must be a non-empty preset name string")
        cleaned = item.strip()
        if cleaned.startswith("preset:"):
            cleaned = cleaned[len("preset:") :].strip()
            if not cleaned:
                raise ValueError(f"extends[{index}] is missing a preset name after 'preset:' prefix")
        if cleaned in seen:
            continue
        seen.add(cleaned)
        names.append(cleaned)
    return names


def _load_preset_sources(preset_names: list[str]) -> list[PolicySource]:
    sources: list[PolicySource] = []
    for name in preset_names:
        try:
            content = load_preset(name)
            resolved_path = preset_path(name)
        except PresetNotFoundError as exc:
            raise ValueError(str(exc)) from exc
        logger.debug("resolved preset %s -> %s", name, resolved_path)
        sources.append(
            PolicySource(
                kind=PRESET_SOURCE_KIND,
                path=f"preset:{name}",
                content=content,
                block_id=name,
                line_start=None,
            )
        )
    return sources


def load_policy_sources(repo_root: Path | str) -> SourceBundle:
    """Load canonical policy sources for the discovered repository root."""

    discovery = discover_policy_repo(repo_root)
    if not discovery.discovered:
        raise FileNotFoundError(discovery.warnings[0])

    root = Path(discovery.repo_root)
    sources: list[PolicySource] = []

    if discovery.claude_path:
        claude_path = root / discovery.claude_path
        claude_text = claude_path.read_text(encoding="utf-8")
        sources.append(PolicySource(kind="claude_md", path=discovery.claude_path, content=claude_text))
        sources.extend(_extract_inline_blocks(claude_path, claude_text))

    include_patterns = list(DEFAULT_POLICY_GLOBS)
    preset_names: list[str] = []
    if discovery.config_path:
        config_path = root / discovery.config_path
        config_text = config_path.read_text(encoding="utf-8")
        sources.append(PolicySource(kind="compiler_config", path=discovery.config_path, content=config_text))
        include_patterns.extend(_load_include_patterns(config_text, discovery.config_path))
        preset_names = _load_preset_names(config_text, discovery.config_path)

    sources.extend(_load_preset_sources(preset_names))

    seen_policy_paths: set[str] = set()
    for pattern_name in sorted(set(include_patterns)):
        for policy_path in sorted(root.glob(pattern_name)):
            if policy_path.is_file():
                rel = policy_path.relative_to(root).as_posix()
                if rel in seen_policy_paths:
                    continue
                seen_policy_paths.add(rel)
                sources.append(
                    PolicySource(kind="policy_file", path=rel, content=policy_path.read_text(encoding="utf-8"))
                )

    logger.debug("loaded %d sources from %s", len(sources), root)
    return SourceBundle(repo_root=str(root), sources=sources, discovery=discovery)
