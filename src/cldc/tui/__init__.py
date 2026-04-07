"""Textual TUI for `cldc`.

Entry point: `cldc tui` -> `cldc.tui.app.run_tui`.
The TUI wraps the pure-core library (ingest / parser / compiler / runtime)
behind an interactive, reactive-state-driven screen. Everything the TUI
does is a thin call into the library; no business logic lives here.
"""

from __future__ import annotations

from cldc.tui.app import CldcApp, run_tui

__all__ = ["CldcApp", "run_tui"]
