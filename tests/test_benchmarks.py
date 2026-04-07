"""Performance benchmarks for the cldc hot paths.

Run with:
    uv run pytest tests/test_benchmarks.py --benchmark-only

These are excluded from the default pytest run via the `benchmark` marker so
they don't slow down normal CI. Track trends over time by exporting the
benchmark JSON with `--benchmark-json=bench.json`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cldc.compiler.policy_compiler import compile_repo_policy
from cldc.runtime.evaluator import (
    _matches_any,
    _matching_commands,
    _normalize_paths,
    check_repo_policy,
)

pytestmark = pytest.mark.benchmark

FIXTURE_REPO_A = Path(__file__).parent / 'fixtures' / 'repo_a'


def _copy_fixture_repo(source_root: Path, destination_root: Path) -> None:
    """Recursively copy a fixture repo into a writable destination."""
    for source in source_root.rglob('*'):
        if not source.is_file():
            continue
        destination = destination_root / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


@pytest.fixture
def large_rule_repo(tmp_path):
    """A repo with 50 deny_write rules across varied glob patterns."""
    rule_blocks = [
        (
            f"  - id: rule-{i:03d}\n"
            f"    kind: deny_write\n"
            f"    mode: block\n"
            f"    paths: ['generated-{i}/**', '**/*.gen.{i}.json']\n"
            f"    message: generated artifact {i}\n"
        )
        for i in range(50)
    ]
    rules_yaml = "rules:\n" + "".join(rule_blocks)
    (tmp_path / 'CLAUDE.md').write_text(
        "```cldc\n" + rules_yaml + "```\n",
        encoding="utf-8",
    )
    compile_repo_policy(tmp_path)
    return tmp_path


@pytest.fixture
def fixture_repo(tmp_path):
    """The canonical test fixture repo, compiled into tmp_path."""
    _copy_fixture_repo(FIXTURE_REPO_A, tmp_path)
    compile_repo_policy(tmp_path)
    return tmp_path


def test_compile_fixture_repo_benchmark(benchmark, tmp_path):
    target = tmp_path / 'repo'
    target.mkdir()
    _copy_fixture_repo(FIXTURE_REPO_A, target)
    result = benchmark(compile_repo_policy, target)
    assert result.rule_count >= 1


def test_check_fixture_repo_benchmark(benchmark, fixture_repo):
    def run():
        return check_repo_policy(
            fixture_repo,
            read_paths=['docs/rfcs/CLDC-0006-validator-engine.md'],
            write_paths=['src/main.py'],
            commands=['pytest -q'],
        )
    report = benchmark(run)
    assert report.decision in {'pass', 'warn', 'block'}


def test_check_against_50_rule_repo_benchmark(benchmark, large_rule_repo):
    def run():
        return check_repo_policy(
            large_rule_repo,
            write_paths=['generated-7/output.json', 'src/app.py', 'tests/test_app.py'],
        )
    report = benchmark(run)
    assert report.decision == 'block'


def test_normalize_paths_1000_paths_benchmark(benchmark, tmp_path):
    paths = [f'src/module_{i}/file_{i}.py' for i in range(1000)]
    result = benchmark(_normalize_paths, paths, repo_root=tmp_path)
    assert len(result) == 1000


def test_matches_any_50_patterns_benchmark(benchmark):
    patterns = [f'generated-{i}/**' for i in range(50)] + [f'**/*.gen.{i}.json' for i in range(50)]
    result = benchmark(_matches_any, 'generated-42/output.bin', patterns)
    assert result is True


def test_matching_commands_benchmark(benchmark):
    commands = [f'cmd-{i}' for i in range(200)]
    expected = [f'cmd-{i}' for i in range(0, 200, 10)]
    result = benchmark(_matching_commands, commands, expected)
    assert len(result) == 20
