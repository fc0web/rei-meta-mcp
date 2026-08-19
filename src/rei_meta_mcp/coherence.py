"""Coherence check — the heart of the tool.

Compares fingerprints across sources pointing at the same object.
§4: unreachable is not coherent. single_source is not coherent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rei_meta_mcp.adapters import build_adapter
from rei_meta_mcp.adapters.base import UnreachableError
from rei_meta_mcp.fingerprint import (
    compute_full_fingerprint,
    compute_partial_fingerprint,
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


def check_coherence(
    registry: Registry,
    object_name: str,
    detail: bool = False,
) -> dict[str, Any]:
    """Run coherence check for one object across all its sources."""
    if object_name not in registry.objects:
        return {
            "object": object_name,
            "status": "unknown_object",
            "checked_at": _now_iso(),
            "sources": [],
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
            "divergence": None,
            "warnings": [f"object {object_name!r} has no registered sources"],
        }

    probes = [_probe_source(s, obj) for s in sources]

    reachable = [p for p in probes if p["reachable"]]
    unreachable = [p for p in probes if not p["reachable"]]

    warnings: list[str] = []
    if unreachable:
        names = [p["name"] for p in unreachable]
        warnings.append(
            "UNCHECKED: " + ", ".join(names)
            + " — 'not checked' is NOT 'coherent' (§4)"
        )

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
        if not disagreements:
            status = "coherent"
            divergence = None
        else:
            status = "divergent"
            counts = {
                p["name"]: p["fingerprint"]["record_count"] for p in reachable
            }
            latest_ids = {
                p["name"]: (
                    p["fingerprint"].get("latest_id")
                    or p["fingerprint"].get("latest_timestamp")
                )
                for p in reachable
            }
            divergence = {
                "count_diff": counts,
                "latest_diff": latest_ids,
                "disagreements": disagreements,
                "only_in": None,
                "content_diff": None,
            }
            if detail:
                divergence["only_in"] = _detail_only_in(sources, obj, probes)

    return {
        "object": object_name,
        "status": status,
        "checked_at": _now_iso(),
        "sources": probes,
        "divergence": divergence,
        "warnings": warnings,
    }


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
