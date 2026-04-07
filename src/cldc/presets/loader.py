"""Discover and load bundled preset policy packs.

Presets live under `src/cldc/presets/packs/` as versioned YAML files, one
per pack. The loader exposes a small, deterministic API so the source
loader and the CLI can agree on preset identity and content without
re-implementing filesystem lookups.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cldc._logging import get_logger
from cldc.errors import PresetNotFoundError  # re-export

logger = get_logger(__name__)

PRESET_SOURCE_KIND = "preset"
_PACKS_DIR = Path(__file__).parent / "packs"
_PRESET_SUFFIX = ".yml"

__all__ = [
    "PRESET_SOURCE_KIND",
    "PresetMetadata",
    "PresetNotFoundError",
    "list_presets",
    "load_preset",
    "preset_path",
]


@dataclass(frozen=True)
class PresetMetadata:
    """Canonical identity of a bundled preset."""

    name: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        """Return `{"name": ..., "path": ...}` for JSON output."""
        return {"name": self.name, "path": str(self.path)}


def _packs_dir() -> Path:
    return _PACKS_DIR


def list_presets() -> list[PresetMetadata]:
    """Return every bundled preset, sorted by name for deterministic output."""

    packs_dir = _packs_dir()
    logger.debug("listing presets from %s", packs_dir)
    if not packs_dir.is_dir():
        return []
    entries: list[PresetMetadata] = []
    for candidate in sorted(packs_dir.iterdir()):
        if candidate.is_file() and candidate.suffix == _PRESET_SUFFIX:
            entries.append(PresetMetadata(name=candidate.stem, path=candidate))
    return entries


def preset_path(name: str) -> Path:
    """Return the path of a bundled preset or raise if it does not exist."""

    cleaned = (name or "").strip()
    if not cleaned:
        raise PresetNotFoundError("preset name must be a non-empty string")
    candidate = _packs_dir() / f"{cleaned}{_PRESET_SUFFIX}"
    if not candidate.is_file():
        available = ", ".join(preset.name for preset in list_presets()) or "<none>"
        raise PresetNotFoundError(f"preset {cleaned!r} is not bundled with this cldc version; available: {available}")
    logger.debug("loading preset %s from %s", cleaned, candidate)
    return candidate


def load_preset(name: str) -> str:
    """Read the raw YAML content of a bundled preset by name."""

    return preset_path(name).read_text(encoding="utf-8")
