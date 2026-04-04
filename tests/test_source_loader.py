
from pathlib import Path

from cldc.ingest.source_loader import load_policy_sources


def test_load_policy_sources_collects_all_supported_inputs():
    repo = Path(__file__).parent / 'fixtures' / 'repo_a'

    bundle = load_policy_sources(repo)

    assert [source.kind for source in bundle.sources] == [
        'claude_md',
        'inline_block',
        'compiler_config',
        'policy_file',
    ]
    assert bundle.sources[0].path == 'CLAUDE.md'
    assert bundle.sources[1].block_id == 'CLAUDE.md:6'
    assert bundle.sources[2].path == '.claude-compiler.yaml'
    assert bundle.sources[3].path == 'policies/commands.yml'


def test_load_policy_sources_is_deterministic():
    repo = Path(__file__).parent / 'fixtures' / 'repo_a'

    first = load_policy_sources(repo)
    second = load_policy_sources(repo)

    assert first.to_dict() == second.to_dict()
