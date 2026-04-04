from pathlib import Path

from cldc.ingest.discovery import discover_policy_repo
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
    assert bundle.discovery.repo_root == str(repo.resolve())


def test_load_policy_sources_is_deterministic():
    repo = Path(__file__).parent / 'fixtures' / 'repo_a'

    first = load_policy_sources(repo)
    second = load_policy_sources(repo)

    assert first.to_dict() == second.to_dict()


def test_discovery_walks_up_from_nested_path(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# top\n')
    nested = tmp_path / 'src' / 'pkg'
    nested.mkdir(parents=True)

    discovery = discover_policy_repo(nested)

    assert discovery.discovered is True
    assert discovery.repo_root == str(tmp_path.resolve())
    assert discovery.claude_path == 'CLAUDE.md'


def test_loader_supports_yml_config_variant(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('# ok\n')
    (tmp_path / '.claude-compiler.yml').write_text('default_mode: block\n')

    bundle = load_policy_sources(tmp_path)

    assert bundle.discovery.config_path == '.claude-compiler.yml'
    assert bundle.sources[1].path == '.claude-compiler.yml'
