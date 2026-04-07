"""Bundled opinionated policy packs for `cldc`.

Presets are referenced by name in `.claude-compiler.yaml` via `extends: [NAME]`
and are loaded as additional policy sources during compilation. Each preset
ships as a versioned YAML document under `packs/` and is discovered by
`list_presets` / `load_preset`.
"""

from cldc.presets.loader import (
    PRESET_SOURCE_KIND,
    PresetNotFoundError,
    list_presets,
    load_preset,
    preset_path,
)

__all__ = [
    "PRESET_SOURCE_KIND",
    "PresetNotFoundError",
    "list_presets",
    "load_preset",
    "preset_path",
]
