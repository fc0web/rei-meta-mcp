"""Regression fixture for the 2026-08-19 incident.

Two sources point to SEED_KERNEL:
  - rei-memory-local: 1,677 theories (HEAD)
  - rei-aios (deployed 2026-08-06): 1,675 theories

Nobody noticed the 11-day drift until a human compared the two numbers.
This test locks in the shape of the detection: divergent + count 1677/1675
+ only_in lists the two extra IDs. If this test ever fails, the raison
d'être of the tool has slipped.
"""

from __future__ import annotations

from rei_meta_mcp.coherence import check_coherence
from rei_meta_mcp.registry import load_registry


def test_incident_1677_vs_1675_is_detected(two_db_count_diff, make_registry):
    local_db, stale_db = two_db_count_diff
    yaml = f"""
version: 1
objects:
  seed_kernel:
    description: "SEED_KERNEL — incident 2026-08-19"
    identity_key: id
sources:
  - name: rei-memory-local
    object: seed_kernel
    kind: sqlite
    config:
      path: "{local_db.as_posix()}"
      table: theories
  - name: rei-aios-stale
    object: seed_kernel
    kind: sqlite
    config:
      path: "{stale_db.as_posix()}"
      table: theories
"""
    reg = load_registry(make_registry(yaml))
    report = check_coherence(reg, "seed_kernel", detail=True)

    assert report["status"] == "divergent", (
        f"expected divergent (the whole point of this tool), got {report['status']!r}"
    )

    counts = report["divergence"]["count_diff"]
    assert counts["rei-memory-local"] == 1677
    assert counts["rei-aios-stale"] == 1675

    only_in = report["divergence"]["only_in"]
    # The two IDs the stale copy is missing:
    assert "seed-01675" in only_in["rei-memory-local"]
    assert "seed-01676" in only_in["rei-memory-local"]
    assert only_in["rei-aios-stale"] == []


def test_incident_reversed_would_also_be_detected(two_db_count_diff, make_registry):
    """§6: the tool must not encode a direction. 'stale' side being the
    smaller one is coincidental; register roles reversed and detection
    still works."""
    local_db, stale_db = two_db_count_diff
    yaml = f"""
version: 1
objects:
  seed_kernel:
    description: "reversed roles"
    identity_key: id
sources:
  - name: bigger
    object: seed_kernel
    kind: sqlite
    config:
      path: "{stale_db.as_posix()}"
      table: theories
  - name: smaller
    object: seed_kernel
    kind: sqlite
    config:
      path: "{local_db.as_posix()}"
      table: theories
"""
    reg = load_registry(make_registry(yaml))
    report = check_coherence(reg, "seed_kernel", detail=True)
    assert report["status"] == "divergent"
    # The tool must not "recommend" which side is correct — just detect.
    # Warnings should not encode a direction.
    for w in report["warnings"]:
        assert "correct" not in w.lower()
        assert "wrong" not in w.lower()
