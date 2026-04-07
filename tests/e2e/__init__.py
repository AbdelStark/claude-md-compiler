"""End-to-end tests for `cldc` against real upstream repositories.

Every test in this package is marked `@pytest.mark.e2e` and is excluded
from the default pytest run (`addopts = "-m 'not e2e'"`). Run the suite
explicitly with `make e2e` or `uv run pytest -m e2e`.

These tests require network access (to clone the upstream repo) and a
`git` executable on PATH. Both are checked at collection time; missing
prerequisites produce a clean `pytest.skip`.
"""
