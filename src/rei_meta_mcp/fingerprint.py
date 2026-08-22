"""Fingerprint computation.

Two flavours:
  - full:    count + id_set_hash + content_hash + latest_timestamp
             (usable when we can enumerate all records: sqlite adapter)
  - partial: count + latest_id + categories_hash
             (usable when adapter only exposes a status endpoint: mcp_stdio)

A `divergent` verdict is possible with either flavour: count mismatch alone
is sufficient. content_hash comparison requires both sides to be full.

Comparison canonical form
-------------------------
Cross-flavour comparison (full vs partial) must NOT coerce type-different
fields into one slot. `latest_timestamp` (ISO-8601 datetime string) and
`latest_id` (arbitrary identifier string) live in different value spaces;
comparing them with `!=` yields a spurious "differs" for every real pair.
See `fingerprint_canonical` for the type-preserving view used by
`fingerprints_agree`.

Out of scope (visible debt)
---------------------------
This module provides `fingerprint_canonical` — a canonical view of a
fingerprint record for cross-source comparison. It does NOT provide
`theory_canonical(T)` — the canonical form of an arbitrary theory
representation that would let `dfumt-content-address-retrieval` compute
CID = SHA-256(canonical(T)). That is a separate function, deliberately
unimplemented here so the hypothesis-tier theory keeps its unmet
dependency visible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_full_fingerprint(
    records: list[dict[str, Any]],
    id_key: str = "id",
    body_key: str = "body",
    updated_at_key: str = "updated_at",
) -> dict[str, Any]:
    """Full fingerprint. Order-independent by design."""
    if not records:
        return {
            "flavour": "full",
            "record_count": 0,
            "id_set_hash": _sha256_hex(""),
            "content_hash": _sha256_hex(""),
            "latest_timestamp": None,
        }

    sorted_ids = sorted(str(r[id_key]) for r in records)
    id_set_hash = _sha256_hex("\n".join(sorted_ids))

    sorted_content = sorted(
        (str(r[id_key]), str(r.get(body_key, ""))) for r in records
    )
    content_hash = _sha256_hex(
        "\n".join(f"{i}\x00{b}" for i, b in sorted_content)
    )

    latest_timestamp: str | None = None
    for r in records:
        ts = r.get(updated_at_key)
        if ts is None:
            continue
        ts_str = str(ts)
        if latest_timestamp is None or ts_str > latest_timestamp:
            latest_timestamp = ts_str

    return {
        "flavour": "full",
        "record_count": len(records),
        "id_set_hash": id_set_hash,
        "content_hash": content_hash,
        "latest_timestamp": latest_timestamp,
    }


def compute_partial_fingerprint(
    record_count: int,
    latest_id: str | None,
    categories: dict[str, int] | None = None,
    source_payload_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Partial fingerprint from status-endpoint style responses.

    categories is treated as a mapping of category name -> count.
    Sorted before hashing so order does not affect the result.

    source_payload_keys (Phase 2): the actual top-level keys returned by
    the adapter's underlying tool. Used by coherence._check_contract to
    compare against object.expected_fields. Passed through, not hashed.
    """
    if categories:
        joined = "\n".join(
            f"{k}\x00{v}" for k, v in sorted(categories.items())
        )
        categories_hash = _sha256_hex(joined)
    else:
        categories_hash = None

    return {
        "flavour": "partial",
        "record_count": record_count,
        "latest_id": latest_id,
        "categories_hash": categories_hash,
        "source_payload_keys": (
            sorted(source_payload_keys) if source_payload_keys else None
        ),
    }


def fingerprint_canonical(fp: dict[str, Any]) -> dict[str, Any]:
    """Return a type-preserving canonical view of a fingerprint.

    Purpose: make cross-flavour comparison sound. `latest_id` (arbitrary
    identifier) and `latest_timestamp` (ISO-8601 datetime) live in
    different value spaces. Previously `fingerprints_agree` coerced them
    into a single slot with `latest_id or latest_timestamp`, then compared
    with `!=`, which is a spurious "differs" for every real cross-flavour
    pair — a full source's timestamp string can never equal a partial
    source's id string.

    The canonical view keeps them in separate slots. Fields absent on the
    given flavour become None; consumers must treat None-vs-value as
    "cannot compare on this field" (silence, not agreement, and not
    disagreement).

    Determinism floor
    -----------------
    Calling this function twice on the same input MUST return equal dicts
    whose JSON serialization is byte-identical. See
    `serialize_fingerprint_canonical` and the accompanying test.

    Scope note
    ----------
    This is `fingerprint_canonical`, not `theory_canonical`. The latter —
    used by `dfumt-content-address-retrieval` for CID = SHA-256(canonical(T))
    — is a separate function and is intentionally NOT implemented here.
    The naming split is deliberate: filling this slot must not read as
    filling the theory-CID dependency.
    """
    flavour = fp.get("flavour")
    return {
        "flavour": flavour,
        "record_count": fp.get("record_count"),
        # full-only fields
        "content_hash": fp.get("content_hash") if flavour == "full" else None,
        "id_set_hash": fp.get("id_set_hash") if flavour == "full" else None,
        "latest_timestamp": fp.get("latest_timestamp") if flavour == "full" else None,
        # partial-only fields
        "latest_id": fp.get("latest_id") if flavour == "partial" else None,
        "categories_hash": fp.get("categories_hash") if flavour == "partial" else None,
    }


def serialize_fingerprint_canonical(fp: dict[str, Any]) -> bytes:
    """Deterministic bytes for the canonical view. Floor-test helper.

    `sort_keys=True` + no whitespace + UTF-8 → any two calls on the same
    fingerprint yield byte-identical output. Callable on either a raw
    fingerprint or an already-canonicalized dict; idempotent.
    """
    canonical = fingerprint_canonical(fp)
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fingerprints_agree(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
    """Return (agree, reason).

    Uses fingerprint_canonical so cross-flavour comparison never coerces
    type-different fields into one slot. Comparison rules:

      - record_count: always compared (both flavours have it).
      - content_hash: compared only when both sides are 'full'.
      - latest_timestamp: compared only when both sides expose it (full × full).
      - latest_id: compared only when both sides expose it (partial × partial).
      - categories_hash: compared only when both sides expose it (partial × partial).

    Cross-flavour (full × partial) intentionally checks only record_count.
    Silence on unavailable fields is neither agreement nor disagreement.
    A partial-side source cannot "prove" a full-side source's content
    unchanged; that is what upgrading the adapter is for.
    """
    ca = fingerprint_canonical(a)
    cb = fingerprint_canonical(b)

    if ca["record_count"] != cb["record_count"]:
        return False, "record_count differs"

    if ca["flavour"] == "full" and cb["flavour"] == "full":
        if ca["content_hash"] != cb["content_hash"]:
            return False, "content_hash differs (records edited)"
        return True, "content_hash matches"

    checked: list[str] = ["record_count"]

    # latest_timestamp: only when both sides are full (spec: full-only field)
    if ca["latest_timestamp"] is not None and cb["latest_timestamp"] is not None:
        if ca["latest_timestamp"] != cb["latest_timestamp"]:
            return False, "latest_timestamp differs"
        checked.append("latest_timestamp")

    # latest_id: only when both sides are partial (spec: partial-only field)
    if ca["latest_id"] is not None and cb["latest_id"] is not None:
        if ca["latest_id"] != cb["latest_id"]:
            return False, "latest_id differs"
        checked.append("latest_id")

    # categories_hash: only when both sides are partial
    if ca["categories_hash"] is not None and cb["categories_hash"] is not None:
        if ca["categories_hash"] != cb["categories_hash"]:
            return False, "categories_hash differs"
        checked.append("categories_hash")

    return True, f"agree on: {', '.join(checked)}"
