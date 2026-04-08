"""Tests for the package-version resolver in `cldc.__init__`.

`cldc.__version__` is normally read from installed package metadata. When the
package is imported from a source checkout that has not been installed —
which happens during local development — the resolver falls back to reading
the `version` field out of `pyproject.toml`. These tests cover both branches
of the fallback so refactors do not silently regress to `"0.0.0"`.
"""

from __future__ import annotations

from pathlib import Path

import cldc
from cldc import _read_source_version, _resolve_version


def test_package_version_matches_pyproject():
    expected = _read_source_version()
    assert cldc.__version__ == expected
    assert expected != "0.0.0", (
        "the source-version fallback returned the sentinel; either pyproject.toml is "
        "missing a [project].version field or the resolver is reading the wrong file"
    )


def test_read_source_version_reads_pyproject_toml():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml should ship at the repo root"

    version_str = _read_source_version()
    assert isinstance(version_str, str)
    # Format check: SemVer-ish "MAJOR.MINOR.PATCH" with optional prerelease.
    parts = version_str.split(".")
    assert len(parts) >= 3, f"unexpected version shape: {version_str!r}"
    assert all(part for part in parts), f"empty segment in version: {version_str!r}"


def test_resolve_version_prefers_source_checkout_version(monkeypatch):
    monkeypatch.setattr(cldc, "_read_source_version", lambda: "0.1.1")
    monkeypatch.setattr(cldc, "_read_installed_version", lambda: "0.1.0")

    assert _resolve_version() == "0.1.1"


def test_resolve_version_falls_back_to_installed_metadata(monkeypatch):
    monkeypatch.setattr(cldc, "_read_source_version", lambda: "0.0.0")
    monkeypatch.setattr(cldc, "_read_installed_version", lambda: "0.1.1")

    assert _resolve_version() == "0.1.1"


def test_read_source_version_falls_back_when_pyproject_missing(monkeypatch, tmp_path):
    """The fallback returns the `0.0.0` sentinel when pyproject.toml is unreachable."""

    # Pretend the package is installed at a path with no parent pyproject.toml.
    fake_module_path = tmp_path / "site-packages" / "cldc" / "__init__.py"
    fake_module_path.parent.mkdir(parents=True)
    fake_module_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(cldc, "__file__", str(fake_module_path))

    assert _read_source_version() == "0.0.0"
