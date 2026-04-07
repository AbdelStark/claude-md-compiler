"""Unit and CLI tests for `cldc hook` (`cldc.runtime.hooks`)."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from cldc.runtime.hooks import (
    CLAUDE_SETTINGS_PATH,
    GIT_PRE_COMMIT_HOOK_PATH,
    HookError,
    generate_claude_code_settings,
    generate_git_pre_commit,
    generate_hook,
    install_git_pre_commit,
    install_hook,
)

PYTHONPATH_ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}


def _init_bare_git_repo(target: Path) -> None:
    subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)


def test_generate_git_pre_commit_returns_executable_artifact():
    artifact = generate_git_pre_commit()

    assert artifact.kind == "git-pre-commit"
    assert artifact.target_path == GIT_PRE_COMMIT_HOOK_PATH
    assert artifact.executable is True
    assert artifact.content.startswith("#!/bin/sh")
    assert "cldc ci" in artifact.content
    assert "--staged" in artifact.content


def test_generate_claude_code_settings_returns_valid_json():
    artifact = generate_claude_code_settings()

    assert artifact.kind == "claude-code"
    assert artifact.target_path == CLAUDE_SETTINGS_PATH
    assert artifact.executable is False

    payload = json.loads(artifact.content)
    assert "hooks" in payload
    post_tool_use = payload["hooks"]["PostToolUse"]
    assert isinstance(post_tool_use, list) and post_tool_use
    matchers = post_tool_use[0]
    assert "Edit" in matchers["matcher"]
    nested = matchers["hooks"][0]
    assert nested["type"] == "command"
    assert "cldc check" in nested["command"]


def test_generate_hook_dispatches_by_kind():
    assert generate_hook("git-pre-commit").kind == "git-pre-commit"
    assert generate_hook("claude-code").kind == "claude-code"


def test_generate_hook_rejects_unknown_kind():
    with pytest.raises(HookError, match="unknown hook kind"):
        generate_hook("nope")


def test_install_git_pre_commit_writes_executable_script(tmp_path):
    _init_bare_git_repo(tmp_path)

    report = install_git_pre_commit(tmp_path)

    assert report.action == "created"
    assert report.kind == "git-pre-commit"
    assert Path(report.repo_root) == tmp_path.resolve()
    assert report.target_path == GIT_PRE_COMMIT_HOOK_PATH

    target = tmp_path / GIT_PRE_COMMIT_HOOK_PATH
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("#!/bin/sh")
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_install_git_pre_commit_refuses_overwrite_without_force(tmp_path):
    _init_bare_git_repo(tmp_path)
    install_git_pre_commit(tmp_path)

    with pytest.raises(HookError, match="already exists"):
        install_git_pre_commit(tmp_path)


def test_install_git_pre_commit_overwrites_with_force(tmp_path):
    _init_bare_git_repo(tmp_path)
    target = tmp_path / GIT_PRE_COMMIT_HOOK_PATH
    install_git_pre_commit(tmp_path)
    target.write_text("#!/bin/sh\necho stale\n", encoding="utf-8")

    report = install_git_pre_commit(tmp_path, force=True)

    assert report.action == "updated"
    assert "cldc ci" in target.read_text(encoding="utf-8")


def test_install_git_pre_commit_requires_git_directory(tmp_path):
    with pytest.raises(HookError, match=r"no \.git directory"):
        install_git_pre_commit(tmp_path)


def test_install_git_pre_commit_rejects_missing_repo(tmp_path):
    with pytest.raises(HookError, match="does not exist"):
        install_git_pre_commit(tmp_path / "ghost")


def test_install_hook_dispatches_to_git_pre_commit(tmp_path):
    _init_bare_git_repo(tmp_path)
    report = install_hook("git-pre-commit", tmp_path)
    assert report.kind == "git-pre-commit"


def test_install_hook_rejects_generate_only_kind(tmp_path):
    _init_bare_git_repo(tmp_path)
    with pytest.raises(HookError, match="generate-only"):
        install_hook("claude-code", tmp_path)


def test_install_hook_rejects_unknown_kind(tmp_path):
    _init_bare_git_repo(tmp_path)
    with pytest.raises(HookError, match="unknown installable hook kind"):
        install_hook("does-not-exist", tmp_path)


def test_cli_hook_generate_git_pre_commit_to_stdout(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "hook", "generate", "git-pre-commit"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "#!/bin/sh" in result.stdout
    assert "cldc ci" in result.stdout


def test_cli_hook_generate_claude_code_json(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "hook", "generate", "claude-code", "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "claude-code"
    assert payload["target_path"] == CLAUDE_SETTINGS_PATH
    inner = json.loads(payload["content"])
    assert "hooks" in inner


def test_cli_hook_install_writes_pre_commit_hook(tmp_path):
    _init_bare_git_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cldc.cli.main",
            "hook",
            "install",
            "git-pre-commit",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "created"
    assert (tmp_path / GIT_PRE_COMMIT_HOOK_PATH).exists()


def test_cli_hook_install_force_overwrites(tmp_path):
    _init_bare_git_repo(tmp_path)
    install_git_pre_commit(tmp_path)
    (tmp_path / GIT_PRE_COMMIT_HOOK_PATH).write_text("#!/bin/sh\necho old\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cldc.cli.main",
            "hook",
            "install",
            "git-pre-commit",
            str(tmp_path),
            "--force",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "updated" in result.stdout
    assert "cldc ci" in (tmp_path / GIT_PRE_COMMIT_HOOK_PATH).read_text(encoding="utf-8")


def test_cli_hook_install_refuses_overwrite_without_force(tmp_path):
    _init_bare_git_repo(tmp_path)
    install_git_pre_commit(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cldc.cli.main",
            "hook",
            "install",
            "git-pre-commit",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 1
    assert "already exists" in result.stderr
