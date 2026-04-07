"""Tests for cldc structured logging.

These tests cover the library-vs-CLI logging contract:

- Importing cldc must not emit anything (NullHandler is attached at import).
- `configure_cli_logging` is the only entry point that adds a stderr handler.
- The CLI exposes `--verbose`/`-v` and `--quiet`/`-q` as top-level flags
  that are mutually exclusive.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from cldc._logging import configure_cli_logging
from cldc.compiler.policy_compiler import compile_repo_policy

PYTHONPATH_ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
FIXTURE_REPO = Path(__file__).parent / "fixtures" / "repo_a"


def _copy_fixture_repo(target: Path) -> None:
    target.mkdir()
    for source in FIXTURE_REPO.rglob("*"):
        if source.is_file():
            destination = target / source.relative_to(FIXTURE_REPO)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_library_is_silent_by_default(tmp_path, caplog):
    target = tmp_path / "repo"
    _copy_fixture_repo(target)

    with caplog.at_level(logging.WARNING, logger="cldc"):
        compile_repo_policy(target)

    noisy_records = [record for record in caplog.records if record.name.startswith("cldc")]
    assert noisy_records == [], (
        "library import or compile_repo_policy emitted unexpected WARNING+ records: "
        f"{[(r.name, r.levelname, r.message) for r in noisy_records]}"
    )


def test_verbose_flag_emits_debug_records(tmp_path, caplog):
    target = tmp_path / "repo"
    _copy_fixture_repo(target)

    configure_cli_logging(verbose=True)
    try:
        with caplog.at_level(logging.DEBUG, logger="cldc"):
            compile_repo_policy(target)
    finally:
        # Reset the logger tree so other tests inherit a clean state.
        configure_cli_logging(verbose=False, quiet=False)
        logging.getLogger("cldc").setLevel(logging.WARNING)

    debug_records = [
        record for record in caplog.records if record.name.startswith("cldc") and record.levelno == logging.DEBUG
    ]
    assert debug_records, "expected at least one DEBUG record under the cldc.* hierarchy"


def test_configure_cli_logging_rejects_both_flags():
    with pytest.raises(ValueError):
        configure_cli_logging(verbose=True, quiet=True)


def test_cli_verbose_flag_produces_debug_output(tmp_path):
    target = tmp_path / "repo"
    _copy_fixture_repo(target)

    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "--verbose", "compile", str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "DEBUG cldc." in result.stderr, (
        "expected DEBUG records on stderr in verbose mode, got stderr:\n" + result.stderr
    )


def test_cli_verbose_and_quiet_are_mutually_exclusive(tmp_path):
    target = tmp_path / "repo"
    _copy_fixture_repo(target)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cldc.cli.main",
            "--verbose",
            "--quiet",
            "compile",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode != 0, "expected non-zero exit when --verbose and --quiet are combined"
