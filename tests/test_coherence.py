"""Coherence check — the §4 verdicts."""

from __future__ import annotations

from rei_meta_mcp.coherence import check_coherence
from rei_meta_mcp.registry import load_registry


def _yaml_two_sqlite(a_path, b_path) -> str:
    return f"""
version: 1
objects:
  seed_kernel:
    description: "SEED_KERNEL"
    identity_key: id
sources:
  - name: source_a
    object: seed_kernel
    kind: sqlite
    config:
      path: "{a_path.as_posix()}"
      table: theories
  - name: source_b
    object: seed_kernel
    kind: sqlite
    config:
      path: "{b_path.as_posix()}"
      table: theories
"""


def test_coherent_when_identical(two_db_identical, make_registry):
    a, b = two_db_identical
    reg = load_registry(make_registry(_yaml_two_sqlite(a, b)))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "coherent"
    assert r["divergence"] is None
    assert all(s["reachable"] for s in r["sources"])


def test_divergent_on_count_diff(two_db_count_diff, make_registry):
    """The 2026-08-19 incident: 1677 vs 1675 must produce `divergent`."""
    a, b = two_db_count_diff
    reg = load_registry(make_registry(_yaml_two_sqlite(a, b)))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "divergent"
    counts = r["divergence"]["count_diff"]
    assert counts["source_a"] == 1677
    assert counts["source_b"] == 1675


def test_divergent_on_id_swap(two_db_same_count_diff_ids, make_registry):
    a, b = two_db_same_count_diff_ids
    reg = load_registry(make_registry(_yaml_two_sqlite(a, b)))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "divergent"


def test_divergent_on_body_edit(two_db_same_ids_diff_body, make_registry):
    a, b = two_db_same_ids_diff_body
    reg = load_registry(make_registry(_yaml_two_sqlite(a, b)))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "divergent"


def test_unreachable_never_coherent(make_registry, two_db_identical):
    """§4 core: one bad source poisons the report — never `coherent`."""
    good, _ = two_db_identical
    yaml = f"""
version: 1
objects:
  seed_kernel:
    description: "x"
    identity_key: id
sources:
  - name: good
    object: seed_kernel
    kind: sqlite
    config:
      path: "{good.as_posix()}"
      table: theories
  - name: bad
    object: seed_kernel
    kind: sqlite
    config:
      path: "/definitely/does/not/exist.db"
      table: theories
"""
    reg = load_registry(make_registry(yaml))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] != "coherent"
    assert r["status"] == "single_source"  # only 1 reachable
    assert any("UNCHECKED" in w for w in r["warnings"])


def test_all_unreachable_gives_unreachable(make_registry):
    yaml = """
version: 1
objects:
  seed_kernel:
    description: "x"
    identity_key: id
sources:
  - name: a
    object: seed_kernel
    kind: sqlite
    config: {path: "/no/such/a.db", table: theories}
  - name: b
    object: seed_kernel
    kind: sqlite
    config: {path: "/no/such/b.db", table: theories}
"""
    reg = load_registry(make_registry(yaml))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "unreachable"
    assert r["divergence"] is None


def test_single_source_verdict(make_registry, two_db_identical):
    a, _ = two_db_identical
    yaml = f"""
version: 1
objects:
  seed_kernel:
    description: "x"
    identity_key: id
sources:
  - name: only_one
    object: seed_kernel
    kind: sqlite
    config: {{path: "{a.as_posix()}", table: theories}}
"""
    reg = load_registry(make_registry(yaml))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "single_source"
    assert any("only 1" in w for w in r["warnings"])


def test_unreachable_placeholder_kind(make_registry, two_db_identical):
    """The `unreachable_placeholder` kind (used for rei-aios-remote) always
    reports an explicit unreachable — never silently coherent."""
    a, _ = two_db_identical
    yaml = f"""
version: 1
objects:
  seed_kernel:
    description: "x"
    identity_key: id
sources:
  - name: local
    object: seed_kernel
    kind: sqlite
    config: {{path: "{a.as_posix()}", table: theories}}
  - name: remote_placeholder
    object: seed_kernel
    kind: unreachable_placeholder
    config: {{reason: "Phase 1 scope excludes remote probe"}}
"""
    reg = load_registry(make_registry(yaml))
    r = check_coherence(reg, "seed_kernel")
    assert r["status"] == "single_source"
    remote = next(s for s in r["sources"] if s["name"] == "remote_placeholder")
    assert not remote["reachable"]
    assert "Phase 1 scope" in remote["error"]


def test_unknown_object(make_registry):
    reg = load_registry(
        make_registry(
            "version: 1\nobjects:\n  known:\n    description: x\n    identity_key: id\nsources: []\n"
        )
    )
    r = check_coherence(reg, "ghost")
    assert r["status"] == "unknown_object"


def test_no_sources_for_object(make_registry):
    reg = load_registry(
        make_registry(
            "version: 1\nobjects:\n  o:\n    description: x\n    identity_key: id\nsources: []\n"
        )
    )
    r = check_coherence(reg, "o")
    assert r["status"] == "no_sources"


def test_detail_only_in_reports_diff(two_db_count_diff, make_registry):
    a, b = two_db_count_diff
    reg = load_registry(make_registry(_yaml_two_sqlite(a, b)))
    r = check_coherence(reg, "seed_kernel", detail=True)
    assert r["status"] == "divergent"
    only_in = r["divergence"]["only_in"]
    assert only_in is not None
    # The two extra IDs (seed-01675, seed-01676) should show up under source_a
    assert "seed-01675" in only_in["source_a"]
    assert "seed-01676" in only_in["source_a"]
    assert only_in["source_b"] == []
