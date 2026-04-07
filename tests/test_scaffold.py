"""Unit tests for `cldc init` scaffolding (`cldc.scaffold`)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import check_repo_policy
from cldc.scaffold import (
    CLAUDE_MD_FILENAME,
    COMPILER_CONFIG_FILENAME,
    InitError,
    initialize_repo_policy,
)

PYTHONPATH_ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}


def test_initialize_repo_policy_creates_config_and_stub_claude_md(tmp_path):
    report = initialize_repo_policy(tmp_path)

    assert report.presets == ["default"]
    assert report.created == sorted([COMPILER_CONFIG_FILENAME, CLAUDE_MD_FILENAME])
    assert report.updated == []
    assert report.skipped == []
    assert Path(report.repo_root) == tmp_path.resolve()
    assert report.next_action.startswith("Run `cldc compile ")

    config = (tmp_path / COMPILER_CONFIG_FILENAME).read_text(encoding="utf-8")
    assert "extends:" in config
    assert "- default" in config
    assert "rules: []" in config

    claude_md = (tmp_path / CLAUDE_MD_FILENAME).read_text(encoding="utf-8")
    assert "```cldc" in claude_md
    assert COMPILER_CONFIG_FILENAME in claude_md


def test_initialize_repo_policy_respects_existing_claude_md(tmp_path):
    (tmp_path / CLAUDE_MD_FILENAME).write_text("# existing\n", encoding="utf-8")

    report = initialize_repo_policy(tmp_path, presets=["default", "strict"])

    assert report.presets == ["default", "strict"]
    assert report.created == [COMPILER_CONFIG_FILENAME]
    assert report.skipped == [CLAUDE_MD_FILENAME]
    # Untouched even though --force could have rewritten the config.
    assert (tmp_path / CLAUDE_MD_FILENAME).read_text(encoding="utf-8") == "# existing\n"


def test_initialize_repo_policy_refuses_to_overwrite_config_without_force(tmp_path):
    initialize_repo_policy(tmp_path)

    with pytest.raises(InitError, match="already exists"):
        initialize_repo_policy(tmp_path)


def test_initialize_repo_policy_overwrites_config_with_force(tmp_path):
    initialize_repo_policy(tmp_path)
    original = (tmp_path / COMPILER_CONFIG_FILENAME).read_text(encoding="utf-8")
    assert "- strict" not in original

    report = initialize_repo_policy(tmp_path, presets=["strict"], force=True)

    assert report.updated == [COMPILER_CONFIG_FILENAME]
    assert report.created == []
    assert report.skipped == [CLAUDE_MD_FILENAME]
    new_config = (tmp_path / COMPILER_CONFIG_FILENAME).read_text(encoding="utf-8")
    assert "- strict" in new_config
    assert "- default" not in new_config


def test_initialize_repo_policy_rejects_unknown_presets(tmp_path):
    with pytest.raises(InitError, match="not bundled"):
        initialize_repo_policy(tmp_path, presets=["does-not-exist"])


def test_initialize_repo_policy_rejects_empty_preset_list(tmp_path):
    with pytest.raises(InitError, match="at least one preset"):
        initialize_repo_policy(tmp_path, presets=[])


def test_initialize_repo_policy_rejects_missing_directory(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(InitError, match="does not exist"):
        initialize_repo_policy(missing)


def test_initialize_repo_policy_dedupes_presets(tmp_path):
    report = initialize_repo_policy(tmp_path, presets=["default", "default", "strict"])

    assert report.presets == ["default", "strict"]
    config = (tmp_path / COMPILER_CONFIG_FILENAME).read_text(encoding="utf-8")
    # The `- default` entry should appear exactly once.
    assert config.count("- default") == 1


def test_initialized_repo_compiles_and_checks_clean(tmp_path):
    """End-to-end: init -> compile -> check, with the default preset live."""

    initialize_repo_policy(tmp_path)
    compiled = compile_repo_policy(tmp_path)
    assert compiled.rule_count >= 2  # default preset ships 2 rules

    report = check_repo_policy(tmp_path, write_paths=["src/app.py"])
    assert report.decision == "pass"
    # The default preset's deny_write should still fire on generated paths.
    blocked = check_repo_policy(tmp_path, write_paths=["generated/out.txt"])
    assert blocked.decision == "block"


def test_cli_init_creates_config_and_stub(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "init", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["presets"] == ["default"]
    assert CLAUDE_MD_FILENAME in payload["created"]
    assert COMPILER_CONFIG_FILENAME in payload["created"]
    assert (tmp_path / COMPILER_CONFIG_FILENAME).exists()
    assert (tmp_path / CLAUDE_MD_FILENAME).exists()


def test_cli_init_refuses_without_force_and_succeeds_with_force(tmp_path):
    first = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "init", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert first.returncode == 0, first.stderr

    second = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "init", str(tmp_path), "--preset", "strict"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert second.returncode == 1
    assert "already exists" in second.stderr

    forced = subprocess.run(
        [
            sys.executable,
            "-m",
            "cldc.cli.main",
            "init",
            str(tmp_path),
            "--preset",
            "strict",
            "--force",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )
    assert forced.returncode == 0, forced.stderr
    payload = json.loads(forced.stdout)
    assert payload["presets"] == ["strict"]
    assert payload["updated"] == [COMPILER_CONFIG_FILENAME]
