"""Phase 2 contract check — expected_fields vs actual payload keys.

§4 discipline extended to contract axis: description ↔ payload drift
must not be silently absorbed into `coherent`. Phase 2A raises warnings
only (verdict enum unchanged).
"""

from __future__ import annotations

from typing import Any

import pytest

from rei_meta_mcp import adapters as adapters_module
from rei_meta_mcp.adapters.base import Adapter, ProbeResult
from rei_meta_mcp.coherence import _check_contract, check_coherence
from rei_meta_mcp.registry import ObjectDef, load_registry


def _probe(
    name: str,
    reachable: bool,
    source_payload_keys: list[str] | None = None,
    flavour: str = "partial",
) -> dict[str, Any]:
    """Build a probe dict shape matching coherence._probe_source's output."""
    if not reachable:
        return {
            "name": name,
            "kind": "mcp_stdio",
            "reachable": False,
            "fingerprint": None,
            "error": "unreachable (stub)",
        }
    fp: dict[str, Any] = {
        "flavour": flavour,
        "record_count": 100,
    }
    if flavour == "partial":
        fp["source_payload_keys"] = (
            sorted(source_payload_keys) if source_payload_keys else None
        )
    return {
        "name": name,
        "kind": "mcp_stdio",
        "reachable": True,
        "fingerprint": fp,
        "error": None,
    }


def _obj(expected: dict[str, str] | None) -> ObjectDef:
    return ObjectDef(
        name="seed_kernel",
        description="test",
        identity_key="id",
        expected_fields=expected,
    )


# -- Unit tests: _check_contract() directly --------------------------------


def test_no_expected_fields_no_contract_warning():
    """Backward compat: object without expected_fields → 0 warnings."""
    obj = _obj(None)
    probes = [_probe("src", True, ["a", "b", "c"])]
    assert _check_contract(obj, probes) == []


def test_contract_matches():
    """Expected set == actual set → 0 warnings."""
    obj = _obj({"totalTheories": "int", "categories": "dict"})
    probes = [_probe("src", True, ["totalTheories", "categories"])]
    assert _check_contract(obj, probes) == []


def test_contract_missing_finding30_shape():
    """finding #30: description claims 'harmony_score' + 'seven_value_distribution'
    but actual payload has neither. Both must appear in the CONTRACT warning."""
    obj = _obj(
        {
            "totalTheories": "int",
            "latestTheoryId": "str",
            "categories": "dict",
            "dfumtValue": "scalar",
            "harmony_score": "float",  # missing from real payload
            "seven_value_distribution": "dict",  # missing from real payload
        }
    )
    probes = [
        _probe(
            "rei-aios-local-mcp",
            True,
            [
                "totalTheories",
                "latestTheoryId",
                "categories",
                "dfumtValue",
            ],
        )
    ]
    warnings = _check_contract(obj, probes)
    assert len(warnings) == 1
    w = warnings[0]
    assert w.startswith("CONTRACT: rei-aios-local-mcp")
    assert "harmony_score" in w
    assert "seven_value_distribution" in w
    assert "missing" in w


def test_contract_extra_undocumented():
    """Payload has fields not declared as expected → CONTRACT warning."""
    obj = _obj({"a": "int"})
    probes = [_probe("src", True, ["a", "b_undocumented", "c_undocumented"])]
    warnings = _check_contract(obj, probes)
    assert len(warnings) == 1
    w = warnings[0]
    assert "b_undocumented" in w
    assert "c_undocumented" in w
    assert "undocumented" in w


def test_contract_only_applies_to_summary_sources():
    """Full-flavour (sqlite) fingerprints have no source_payload_keys →
    contract check is intentionally skipped for records-based adapters."""
    obj = _obj({"totalTheories": "int"})
    # full-flavour probe has no source_payload_keys
    probes = [_probe("sqlite-src", True, None, flavour="full")]
    assert _check_contract(obj, probes) == []


# -- Integration test: check_coherence end-to-end --------------------------


class _StubMcpAdapter(Adapter):
    """Test-only adapter that returns a canned summary with configurable keys.

    Registered via monkeypatch — not exposed as a production kind.
    """

    def probe(self) -> ProbeResult:
        return ProbeResult(
            summary={
                "record_count": self.config.get("record_count", 100),
                "latest_id": self.config.get("latest_id", "stub-latest"),
                "categories": self.config.get("categories"),
                "source_payload_keys": self.config.get(
                    "source_payload_keys", []
                ),
            }
        )


def test_check_coherence_end_to_end_finding30(monkeypatch, tmp_path):
    """Full integration: registry declares expected_fields, stub adapter
    returns a payload missing 2 of them, check_coherence surfaces the
    CONTRACT warning while status stays coherent (Phase 2A design)."""
    orig_build = adapters_module.build_adapter

    def _stub_build(kind: str, config: dict):
        if kind == "stub_mcp":
            return _StubMcpAdapter(config)
        return orig_build(kind, config)

    monkeypatch.setattr(adapters_module, "build_adapter", _stub_build)
    # coherence.py imported build_adapter directly at module load; patch that ref too
    import rei_meta_mcp.coherence as coherence_mod
    monkeypatch.setattr(coherence_mod, "build_adapter", _stub_build)

    yaml = """
version: 1
objects:
  seed_kernel:
    description: "SEED_KERNEL 理論群"
    identity_key: id
    expected_fields:
      totalTheories: int
      latestTheoryId: str
      categories: dict
      dfumtValue: scalar
      harmony_score: float
      seven_value_distribution: dict
sources:
  - name: aios-a
    object: seed_kernel
    kind: stub_mcp
    config:
      record_count: 1677
      latest_id: seed-01676
      source_payload_keys: [totalTheories, latestTheoryId, categories, dfumtValue]
  - name: aios-b
    object: seed_kernel
    kind: stub_mcp
    config:
      record_count: 1677
      latest_id: seed-01676
      source_payload_keys: [totalTheories, latestTheoryId, categories, dfumtValue]
"""
    reg_path = tmp_path / "sources.yaml"
    reg_path.write_text(yaml, encoding="utf-8")
    reg = load_registry(reg_path)

    r = check_coherence(reg, "seed_kernel")
    # Phase 2A: contract mismatch does NOT flip status.
    # STEP 1839: `coherent` renamed to `coherent_on_basis` when the
    # comparison-basis contract landed. Intentional flip — the verdict now
    # states what basis it stands on. Two agreeing partial-flavour stub_mcp
    # sources: meet = {record_count, latest_id, categories_hash}, no
    # unchecked → coherent_on_basis. See coherence.py STEP 1839 header.
    assert r["status"] == "coherent_on_basis"
    # But it DOES surface a CONTRACT warning per source.
    contract_warnings = [w for w in r["warnings"] if w.startswith("CONTRACT:")]
    assert len(contract_warnings) == 2  # one per source
    combined = " ".join(contract_warnings)
    assert "harmony_score" in combined
    assert "seven_value_distribution" in combined
    assert "aios-a" in combined
    assert "aios-b" in combined
