"""Registry parsing."""

from __future__ import annotations

import pytest

from rei_meta_mcp.registry import RegistryError, load_registry


def test_valid_registry(make_registry):
    p = make_registry(
        """
version: 1
objects:
  seed_kernel:
    description: "SEED_KERNEL"
    identity_key: id
sources:
  - name: s1
    object: seed_kernel
    kind: sqlite
    config:
      path: /nonexistent.db
"""
    )
    reg = load_registry(p)
    assert reg.version == 1
    assert "seed_kernel" in reg.objects
    assert len(reg.sources) == 1
    assert reg.sources_for("seed_kernel")[0].name == "s1"


def test_missing_file(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yaml")


def test_malformed_yaml(make_registry):
    p = make_registry("version: 1\n  bad:\n indent")
    with pytest.raises(RegistryError, match="invalid YAML"):
        load_registry(p)


def test_wrong_version(make_registry):
    p = make_registry("version: 2\nobjects: {}\nsources: []\n")
    with pytest.raises(RegistryError, match="unsupported"):
        load_registry(p)


def test_source_references_undefined_object(make_registry):
    p = make_registry(
        """
version: 1
objects:
  seed_kernel:
    description: "x"
    identity_key: id
sources:
  - name: s1
    object: ghost_object
    kind: sqlite
    config: {}
"""
    )
    with pytest.raises(RegistryError, match="undefined object"):
        load_registry(p)


def test_duplicate_source_names(make_registry):
    p = make_registry(
        """
version: 1
objects:
  o:
    description: "x"
    identity_key: id
sources:
  - name: dup
    object: o
    kind: sqlite
    config: {}
  - name: dup
    object: o
    kind: sqlite
    config: {}
"""
    )
    with pytest.raises(RegistryError, match="duplicate"):
        load_registry(p)


def test_source_missing_kind(make_registry):
    p = make_registry(
        """
version: 1
objects:
  o:
    description: "x"
    identity_key: id
sources:
  - name: s1
    object: o
    config: {}
"""
    )
    with pytest.raises(RegistryError, match="missing 'kind'"):
        load_registry(p)
