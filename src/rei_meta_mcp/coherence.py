"""Coherence check — the heart of the tool.

Compares fingerprints across sources pointing at the same object.
§4: unreachable is not coherent. single_source is not coherent.

STEP 1839 (2026-09-06): comparison-basis contract 適合
--------------------------------------------------------
rei-aios STEP 1838 の comparison-basis-contract v0.1 が定義する 4 gate に
機械可読で適合させる:
- 返り値に `comparisonBasis` (10 field) を常時添付
- `coherent` → `coherent_on_basis` に降格 (comparedFields 非空 かつ
  uncheckedSources 空 の ときのみ)
- comparedFields 空 or uncheckedSources 非空 かつ agree → `insufficient_basis`
  (G1 / G4 を機械可読に守る)
- divergence は meet 内の field のみ (record_count 等)。
  meet 外の観測 (latest_id / latest_timestamp の片側欠測) は
  `unavailable_fields` に 別 key で 分離
- `undetectable[]` に 「record_count 保存乖離は 検出不能」 等の
  盲点を 常に 少なくとも 1 件 宣言 (G2)

Breaking change: 従来 `coherent` を状態値として parse していた呼び出しは
`coherent_on_basis` (positive verdict、意図的な降格) を受けるように追随要。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rei_meta_mcp.adapters import build_adapter
from rei_meta_mcp.adapters.base import UnreachableError
from rei_meta_mcp.fingerprint import (
    compute_full_fingerprint,
    compute_partial_fingerprint,
    fingerprint_canonical,
    fingerprints_agree,
)
from rei_meta_mcp.registry import ObjectDef, Registry, SourceDef


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _probe_source(source: SourceDef, obj: ObjectDef) -> dict[str, Any]:
    """Probe one source and return its fingerprint block.

    Never raises — errors are recorded as reachable=False.
    """
    adapter = None
    try:
        adapter = build_adapter(source.kind, source.config)
        result = adapter.probe()
    except UnreachableError as e:
        return {
            "name": source.name,
            "kind": source.kind,
            "reachable": False,
            "fingerprint": None,
            "error": str(e),
        }
    except Exception as e:
        return {
            "name": source.name,
            "kind": source.kind,
            "reachable": False,
            "fingerprint": None,
            "error": f"{type(e).__name__}: {e}",
        }
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                pass

    if result.records is not None:
        fp = compute_full_fingerprint(
            result.records,
            id_key=obj.identity_key,
        )
    elif result.summary is not None:
        fp = compute_partial_fingerprint(
            record_count=result.summary["record_count"],
            latest_id=result.summary.get("latest_id"),
            categories=result.summary.get("categories"),
            source_payload_keys=result.summary.get("source_payload_keys"),
        )
    else:
        return {
            "name": source.name,
            "kind": source.kind,
            "reachable": False,
            "fingerprint": None,
            "error": "adapter returned neither records nor summary",
        }

    return {
        "name": source.name,
        "kind": source.kind,
        "reachable": True,
        "fingerprint": fp,
        "error": None,
    }


def _pairwise_agreement(probes: list[dict[str, Any]]) -> list[str]:
    """Return list of reasons for disagreement across reachable probes."""
    reachable = [p for p in probes if p["reachable"]]
    reasons: list[str] = []
    for i in range(len(reachable)):
        for j in range(i + 1, len(reachable)):
            a = reachable[i]
            b = reachable[j]
            agree, reason = fingerprints_agree(a["fingerprint"], b["fingerprint"])
            if not agree:
                reasons.append(f"{a['name']} vs {b['name']}: {reason}")
    return reasons


def _compute_only_in(
    probes: list[dict[str, Any]],
    limit: int = 100,
) -> dict[str, list[str]] | None:
    """When exactly two full-fingerprint sources with cached ID sets exist,
    compute the ID sets in the differences. Requires records to still be
    around — coherence_report re-runs probing for `detail=True` calls.
    """
    return None  # populated by check_coherence when detail=True


# ────────────────────────────────────────────────
# STEP 1839: comparison-basis contract adapters
# ────────────────────────────────────────────────

# canonical field ordering per fingerprint flavour.
# Kept in sync with fingerprint.fingerprint_canonical() spec — that function
# returns a dict with these keys (record_count present in both flavours;
# flavour-specific fields None when absent).
_FULL_FIELDS = ("record_count", "id_set_hash", "content_hash", "latest_timestamp")
_PARTIAL_FIELDS = ("record_count", "latest_id", "categories_hash")


def _available_fields_of(fp: dict[str, Any] | None) -> list[str]:
    """Return the fingerprint fields the given source actually exposes.

    Uses the canonical view: fields present with non-None value are
    considered available. `flavour` is metadata, not a comparable field.
    """
    if fp is None:
        return []
    canon = fingerprint_canonical(fp)
    fields = _FULL_FIELDS if canon.get("flavour") == "full" else _PARTIAL_FIELDS
    return sorted(k for k in fields if canon.get(k) is not None)


def _classify_separating_power(compared: list[str]) -> str:
    """Map the meet field set to the STEP 1838 SeparatingPower ordinal.

    content > identity-set > multi-scalar > scalar > none.
    """
    if not compared:
        return "none"
    if "content_hash" in compared:
        return "content"
    if "id_set_hash" in compared:
        return "identity-set"
    non_count = [f for f in compared if f != "record_count"]
    if non_count:
        return "multi-scalar"
    return "scalar"


def _undetectable_classes(
    compared: list[str],
    available: dict[str, list[str]],
) -> list[str]:
    """Name the blind spots implied by this meet (G2 requirement).

    Every entry names a concrete class of divergence the basis cannot see,
    not vague reservations. Empty is only allowed when separatingPower is
    'content' (the strongest); the caller respects that gate.
    """
    out: list[str] = []
    if not compared:
        out.append(
            "no comparable fields across sources; nothing is detectable "
            "on this basis"
        )
        return out
    power = _classify_separating_power(compared)
    if power == "scalar":
        out.append(
            "record_count preservation blindness: two sources with the "
            "same count but different record identities or contents "
            "(swap / edit) are indistinguishable on this basis"
        )
    if "content_hash" not in compared:
        out.append(
            "content-level record edits (body change within a preserved "
            "id set) are not detectable without content_hash on both sides"
        )
    if "id_set_hash" not in compared:
        out.append(
            "id-set replacement (same count, different ids) is not "
            "detectable without id_set_hash on both sides"
        )
    # Cross-flavour note when reachable sources disagree on flavour.
    flavours = {
        (fp := (available.get(name, []))) and ("full" if "content_hash" in fp else "partial")
        for name in available
        if available.get(name)
    }
    flavours.discard(None)
    if len(flavours) > 1:
        out.append(
            "cross-flavour comparison (full × partial): only fields "
            "present in every flavour participate in the meet — "
            "everything outside is silence, not agreement"
        )
    return out


def _build_comparison_basis(
    object_name: str,
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the STEP 1838 ComparisonBasis payload for these probes.

    Never raises. Returns the 10-field structure verify.ts expects at the
    contract layer:

      sourcesDeclared   — every registered source name, regardless of reach
      sourcesCompared   — reachable sources that supplied a fingerprint
      uncheckedSources  — sources that failed to be probed (unreachable)
      availableFields   — per source, the fingerprint fields it exposed
      comparedFields    — the meet (intersection) across sourcesCompared
      basisOrigin       — 'intersection' when we derive the meet from data
      separatingPower   — classified by the meet, per SEPARATING_POWER_ORDER
      undetectable      — concrete blind-spot classes for this basis
    """
    sources_declared = [p["name"] for p in probes]
    reachable = [p for p in probes if p["reachable"] and p["fingerprint"] is not None]
    unreachable = [p for p in probes if not (p["reachable"] and p["fingerprint"] is not None)]

    sources_compared = [p["name"] for p in reachable]
    unchecked_sources = [p["name"] for p in unreachable]

    available: dict[str, list[str]] = {}
    for p in reachable:
        available[p["name"]] = _available_fields_of(p["fingerprint"])
    for p in unreachable:
        available[p["name"]] = []

    if len(reachable) >= 2:
        sets = [set(available[name]) for name in sources_compared]
        compared = sorted(set.intersection(*sets))
    else:
        # 0 or 1 reachable → no meet across ≥2 sources → basis is empty.
        compared = []

    power = _classify_separating_power(compared)
    undetectable = _undetectable_classes(compared, available)

    return {
        "gauge": "rei_meta_coherence",
        "unit": object_name,
        "sourcesDeclared": sources_declared,
        "sourcesCompared": sources_compared,
        "uncheckedSources": unchecked_sources,
        "availableFields": available,
        "comparedFields": compared,
        "basisOrigin": "intersection" if compared else "none",
        "separatingPower": power,
        "undetectable": undetectable,
    }


def _split_divergence_by_meet(
    reachable: list[dict[str, Any]],
    meet: list[str],
    disagreements: list[str],
    detail_only_in: dict[str, list[str]] | None,
) -> dict[str, Any]:
    """Return divergence structure with meet-inside vs meet-outside separated.

    STEP 1839 G3 requires: fields not in every source's availableFields must
    not be reported as `*_diff` (a diff implies both sides supplied a
    value). Meet-outside observations go under `unavailable_fields` with a
    per-source value/None map so callers can still see them without
    conflating "absent" with "differs".
    """
    def per_source(field: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for p in reachable:
            canon = fingerprint_canonical(p["fingerprint"])
            result[p["name"]] = canon.get(field)
        return result

    # count_diff is always inside the meet for any 2 reachable sources
    # (record_count is present in every fingerprint flavour).
    div: dict[str, Any] = {
        "count_diff": {p["name"]: p["fingerprint"]["record_count"] for p in reachable},
        "disagreements": disagreements,
        "only_in": detail_only_in,
        "content_diff": None,
    }

    # Every field previously reported as *_diff but not in the meet moves
    # to unavailable_fields with per-source values. This preserves the
    # diagnostic information without lying about a "diff".
    unavailable: dict[str, dict[str, Any]] = {}
    for field in ("latest_id", "latest_timestamp"):
        if field not in meet:
            values = per_source(field)
            if any(v is not None for v in values.values()):
                unavailable[field] = values
    if unavailable:
        div["unavailable_fields"] = unavailable

    return div


def check_coherence(
    registry: Registry,
    object_name: str,
    detail: bool = False,
) -> dict[str, Any]:
    """Run coherence check for one object across all its sources.

    STEP 1839 shape: always emits `comparisonBasis` (the 10-field
    ComparisonBasis from rei-aios STEP 1838 contract). Status values:

      unknown_object    — the object name is not in the registry
      no_sources        — the object is registered but has no sources
      unreachable       — 0 reachable sources
      single_source     — exactly 1 reachable source (no meet possible)
      coherent_on_basis — reachable ≥ 2, all agree, comparedFields non-empty,
                          uncheckedSources empty (G1+G2+G3+G4 all pass)
      insufficient_basis — reachable ≥ 2, all agree, but comparedFields empty
                          (G1 blocked) OR uncheckedSources non-empty (G4 blocked)
      divergent         — pairwise disagreement on meet fields
    """
    if object_name not in registry.objects:
        return {
            "object": object_name,
            "status": "unknown_object",
            "checked_at": _now_iso(),
            "sources": [],
            "comparisonBasis": _build_comparison_basis(object_name, []),
            "divergence": None,
            "warnings": [f"object {object_name!r} not defined in registry"],
        }

    obj = registry.objects[object_name]
    sources = registry.sources_for(object_name)

    if not sources:
        return {
            "object": object_name,
            "status": "no_sources",
            "checked_at": _now_iso(),
            "sources": [],
            "comparisonBasis": _build_comparison_basis(object_name, []),
            "divergence": None,
            "warnings": [f"object {object_name!r} has no registered sources"],
        }

    probes = [_probe_source(s, obj) for s in sources]
    basis = _build_comparison_basis(object_name, probes)

    reachable = [p for p in probes if p["reachable"]]
    unreachable = [p for p in probes if not p["reachable"]]

    warnings: list[str] = []
    if unreachable:
        names = [p["name"] for p in unreachable]
        warnings.append(
            "UNCHECKED: " + ", ".join(names)
            + " — 'not checked' is NOT 'coherent' (§4)"
        )

    warnings.extend(_check_contract(obj, probes))

    if not reachable:
        status = "unreachable"
        divergence = None
    elif len(reachable) == 1:
        status = "single_source"
        warnings.append(
            f"only 1 reachable source ({reachable[0]['name']}); "
            "coherence check not meaningful"
        )
        divergence = None
    else:
        disagreements = _pairwise_agreement(probes)
        if disagreements:
            status = "divergent"
            detail_only_in = _detail_only_in(sources, obj, probes) if detail else None
            divergence = _split_divergence_by_meet(
                reachable=reachable,
                meet=basis["comparedFields"],
                disagreements=disagreements,
                detail_only_in=detail_only_in,
            )
        else:
            # All reachable agree. Now G1 (basis non-empty) and G4
            # (no unchecked) determine whether we can call this coherent.
            g1_ok = len(basis["comparedFields"]) > 0
            g4_ok = len(basis["uncheckedSources"]) == 0
            if g1_ok and g4_ok:
                status = "coherent_on_basis"
                divergence = None
            else:
                # Sources agree on what they can compare, but the basis
                # is either empty (G1) or incomplete (G4). Either way,
                # we must not claim coherence — the contract calls this
                # `insufficient_basis`.
                status = "insufficient_basis"
                divergence = None
                if not g1_ok:
                    warnings.append(
                        "INSUFFICIENT_BASIS: no fields present in every "
                        "reachable source; agreement is vacuous"
                    )
                if not g4_ok:
                    warnings.append(
                        "INSUFFICIENT_BASIS: "
                        f"{len(basis['uncheckedSources'])} source(s) unchecked; "
                        "reachable sources agree only among themselves"
                    )

    return {
        "object": object_name,
        "status": status,
        "checked_at": _now_iso(),
        "sources": probes,
        "comparisonBasis": basis,
        "divergence": divergence,
        "warnings": warnings,
    }


def _check_contract(
    obj: ObjectDef,
    probes: list[dict[str, Any]],
) -> list[str]:
    """Phase 2 contract check: compare each reachable source's actual
    payload keys against the object's declared expected_fields.

    Returns list of warning strings (empty if no expectation declared, or
    every reachable summary-source matches). Never changes the status
    verdict — Phase 2A is warning-only, following §4's discipline of
    "unchecked is not coherent" extended to "contract mismatch is not
    coherent silently".

    Only summary-flavour sources (mcp_stdio) carry `source_payload_keys`;
    full-flavour sources (sqlite records) have fixed schema `id/body/
    updated_at` and are intentionally skipped from contract check.
    """
    if not obj.expected_fields:
        return []
    warnings: list[str] = []
    expected = set(obj.expected_fields.keys())
    for probe in probes:
        if not probe["reachable"]:
            continue
        fp = probe.get("fingerprint") or {}
        actual_keys = fp.get("source_payload_keys")
        if actual_keys is None:
            continue
        actual = set(actual_keys)
        missing = expected - actual
        extra = actual - expected
        if missing:
            warnings.append(
                f"CONTRACT: {probe['name']} — expected fields missing from "
                f"payload: {sorted(missing)} (description ↔ payload drift)"
            )
        if extra:
            warnings.append(
                f"CONTRACT: {probe['name']} — payload has fields not in "
                f"expected: {sorted(extra)} (undocumented)"
            )
    return warnings


def _detail_only_in(
    sources: list[SourceDef],
    obj: ObjectDef,
    prior_probes: list[dict[str, Any]],
    limit: int = 100,
) -> dict[str, list[str]] | None:
    """Re-probe sources that support enumeration and compute set differences.

    Only meaningful across sources whose adapters expose records. Sources
    that only give summaries (mcp_stdio) contribute nothing here.
    """
    id_sets: dict[str, set[str]] = {}
    for source in sources:
        prior = next(
            (p for p in prior_probes if p["name"] == source.name), None
        )
        if prior is None or not prior["reachable"]:
            continue
        adapter = None
        try:
            adapter = build_adapter(source.kind, source.config)
            result = adapter.probe()
        except Exception:
            continue
        finally:
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    pass
        if result.records is None:
            continue
        id_sets[source.name] = {str(r[obj.identity_key]) for r in result.records}

    if len(id_sets) < 2:
        return None

    names = sorted(id_sets.keys())
    only_in: dict[str, list[str]] = {}
    all_ids: set[str] = set().union(*id_sets.values())
    for name in names:
        missing_from_others = id_sets[name] - set().union(
            *[id_sets[n] for n in names if n != name]
        )
        # Report IDs present in this source but absent from every other
        # enumerable source. Capped to `limit` for UI-friendliness.
        only_in[name] = sorted(missing_from_others)[:limit]
    return only_in
