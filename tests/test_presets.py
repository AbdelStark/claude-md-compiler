"""Tests for bundled preset policy packs and their integration points."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy, doctor_repo_policy
from cldc.ingest.source_loader import PRESET_SOURCE_KIND, load_policy_sources
from cldc.parser.rule_parser import parse_rule_documents
from cldc.presets import PresetNotFoundError, list_presets, load_preset, preset_path
from cldc.runtime.evaluator import check_repo_policy

PYTHONPATH_ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}


def test_list_presets_returns_bundled_packs_in_sorted_order():
    presets = list_presets()

    names = [preset.name for preset in presets]
    assert "default" in names
    assert "strict" in names
    assert "docs-sync" in names
    assert names == sorted(names)
    for preset in presets:
        assert preset.path.exists()
        assert preset.path.suffix == ".yml"


def test_load_preset_returns_yaml_content_with_rules():
    content = load_preset("default")
    assert "rules:" in content
    assert "preset-default-generated-read-only" in content
    assert str(preset_path("default")) == str(preset_path("default").resolve())


def test_load_preset_rejects_unknown_name():
    with pytest.raises(PresetNotFoundError, match="not bundled with this cldc version"):
        load_preset("does-not-exist")


def test_load_preset_rejects_empty_name():
    with pytest.raises(PresetNotFoundError, match="non-empty string"):
        load_preset("")


def _minimal_repo_with_extends(tmp_path: Path, extends: list[str]) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# Test repo\n")
    extends_yaml = "\n".join(f"  - {name}" for name in extends)
    (tmp_path / ".claude-compiler.yaml").write_text(f"default_mode: warn\nextends:\n{extends_yaml}\n")
    return tmp_path


def test_load_policy_sources_includes_preset_sources_from_extends(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["default", "strict"])

    bundle = load_policy_sources(tmp_path)

    preset_sources = [source for source in bundle.sources if source.kind == PRESET_SOURCE_KIND]
    assert [source.path for source in preset_sources] == ["preset:default", "preset:strict"]
    assert all(source.content.strip().startswith("#") or "rules:" in source.content for source in preset_sources)
    assert all(source.block_id in {"default", "strict"} for source in preset_sources)


def test_load_policy_sources_deduplicates_extends_entries(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["default", "default", "strict"])

    bundle = load_policy_sources(tmp_path)
    preset_sources = [source for source in bundle.sources if source.kind == PRESET_SOURCE_KIND]

    assert [source.path for source in preset_sources] == ["preset:default", "preset:strict"]


def test_load_policy_sources_supports_preset_prefix_in_extends(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["preset:default"])

    bundle = load_policy_sources(tmp_path)
    preset_sources = [source for source in bundle.sources if source.kind == PRESET_SOURCE_KIND]

    assert [source.path for source in preset_sources] == ["preset:default"]


def test_load_policy_sources_rejects_unknown_preset(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["does-not-exist"])

    with pytest.raises(ValueError, match="preset 'does-not-exist'"):
        load_policy_sources(tmp_path)


def test_load_policy_sources_rejects_malformed_extends(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Test repo\n")
    (tmp_path / ".claude-compiler.yaml").write_text("default_mode: warn\nextends: not-a-list\n")

    with pytest.raises(ValueError, match="extends must be a list"):
        load_policy_sources(tmp_path)


def test_parse_rule_documents_merges_preset_rules_with_user_rules(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["default"])
    (tmp_path / ".claude-compiler.yaml").write_text(
        "default_mode: warn\n"
        "extends:\n"
        "  - default\n"
        "rules:\n"
        "  - id: user-own-rule\n"
        "    kind: deny_write\n"
        "    paths: ['local/**']\n"
        "    message: Local paths are frozen.\n"
    )

    bundle = load_policy_sources(tmp_path)
    parsed = parse_rule_documents(bundle)

    rule_ids = [rule.rule_id for rule in parsed.rules]
    assert "user-own-rule" in rule_ids
    assert "preset-default-generated-read-only" in rule_ids
    assert "preset-default-lockfiles-follow-manifests" in rule_ids


def test_compile_repo_policy_with_presets_enforces_preset_rules(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["default"])
    compile_repo_policy(tmp_path)

    blocked = check_repo_policy(tmp_path, write_paths=["generated/out.json"])
    assert blocked.decision == "block"
    assert any(v.rule_id == "preset-default-generated-read-only" for v in blocked.violations)

    clean = check_repo_policy(tmp_path, write_paths=["src/app.py"])
    assert clean.decision == "pass"


def test_compile_repo_policy_with_strict_preset_enforces_ci_green_claim(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["strict"])
    compile_repo_policy(tmp_path)

    report = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py", "tests/test_app.py"],
        read_paths=["docs/rfcs/001.md"],
    )
    rule_ids = [violation.rule_id for violation in report.violations]
    assert "preset-strict-require-ci-green-claim" in rule_ids
    assert report.decision == "block"

    cleared = check_repo_policy(
        tmp_path,
        write_paths=["src/app.py", "tests/test_app.py"],
        read_paths=["docs/rfcs/001.md"],
        claims=["ci-green"],
    )
    assert cleared.decision == "pass"


def test_compile_repo_policy_with_strict_preset_forbids_raw_pip_install(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["strict"])
    compile_repo_policy(tmp_path)

    blocked = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["pip install"],
        claims=["ci-green"],
    )
    rule_ids = [violation.rule_id for violation in blocked.violations]
    assert "preset-strict-forbid-raw-pip-install" in rule_ids
    assert blocked.decision == "block"

    clean = check_repo_policy(
        tmp_path,
        write_paths=["pyproject.toml"],
        commands=["uv sync --locked"],
        claims=["ci-green"],
    )
    assert "preset-strict-forbid-raw-pip-install" not in [v.rule_id for v in clean.violations]


def test_doctor_repo_policy_with_extends_does_not_crash_on_preset_paths(tmp_path):
    """Regression: `doctor` used to call `Path.stat()` on `preset:*` paths."""

    _minimal_repo_with_extends(tmp_path, ["default"])

    # Before compile: discovery should succeed and lockfile should be reported
    # as missing without raising FileNotFoundError on the preset source path.
    pre_compile = doctor_repo_policy(tmp_path)
    assert pre_compile.discovered is True
    assert pre_compile.lockfile_exists is False
    assert pre_compile.source_count >= 1

    compile_repo_policy(tmp_path)

    # After compile: the staleness check must skip preset sources rather than
    # crashing when it tries to stat a non-existent `preset:default` path.
    post_compile = doctor_repo_policy(tmp_path)
    assert post_compile.discovered is True
    assert post_compile.lockfile_exists is True
    assert post_compile.rule_count >= 2
    assert post_compile.errors == []
    assert not any("appears stale" in warning for warning in post_compile.warnings)


def test_compile_repo_policy_lockfile_rule_count_includes_preset_rules(tmp_path):
    _minimal_repo_with_extends(tmp_path, ["default", "strict"])
    compiled = compile_repo_policy(tmp_path)

    lockfile = tmp_path / ".claude" / "policy.lock.json"
    payload = json.loads(lockfile.read_text())
    assert payload["source_precedence"] == [
        "claude_md",
        "inline_block",
        "compiler_config",
        "preset",
        "policy_file",
    ]
    assert payload["rule_count"] == compiled.rule_count
    assert compiled.rule_count >= 5  # 2 default + 3 strict, plus any user-added rules


def test_cli_preset_list_outputs_bundled_packs():
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "preset", "list", "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["preset_count"] >= 3
    names = [preset["name"] for preset in payload["presets"]]
    assert "default" in names
    assert "strict" in names


def test_cli_preset_list_text_output_hints_at_extends_syntax():
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "preset", "list"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "Bundled presets" in result.stdout
    assert "extends:" in result.stdout


def test_cli_preset_show_prints_raw_yaml():
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "preset", "show", "default"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "rules:" in result.stdout
    assert "preset-default-generated-read-only" in result.stdout


def test_cli_preset_show_json_output_includes_content_and_path():
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "preset", "show", "strict", "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "strict"
    assert "rules:" in payload["content"]
    assert payload["path"].endswith("strict.yml")


def test_cli_preset_show_returns_error_for_unknown_preset():
    result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "preset", "show", "nonexistent", "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    assert "nonexistent" in payload["error"]


def test_cli_compile_with_extends_succeeds_and_includes_preset_rules(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Test repo\n")
    (tmp_path / ".claude-compiler.yaml").write_text("default_mode: warn\nextends:\n  - default\n")

    compile_result = subprocess.run(
        [sys.executable, "-m", "cldc.cli.main", "compile", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=PYTHONPATH_ENV,
    )

    assert compile_result.returncode == 0, compile_result.stderr
    payload = json.loads(compile_result.stdout)
    assert payload["rule_count"] >= 2
    assert "preset" in payload["discovery"]["warnings"] or payload["discovery"].get("warnings") is not None
