"""Fingerprint computation.

Two flavours:
  - full:    count + id_set_hash + content_hash + latest_timestamp
             (usable when we can enumerate all records: sqlite adapter)
  - partial: count + latest_id + categories_hash
             (usable when adapter only exposes a status endpoint: mcp_stdio)

A `divergent` verdict is possible with either flavour: count mismatch alone
is sufficient. content_hash comparison requires both sides to be full.
"""

from __future__ import annotations

import hashlib
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
) -> dict[str, Any]:
    """Partial fingerprint from status-endpoint style responses.

    categories is treated as a mapping of category name -> count.
    Sorted before hashing so order does not affect the result.
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
    }


def fingerprints_agree(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
    """Return (agree, reason).

    If both are full, compare content_hash (strongest).
    If either is partial, compare count + latest_id + categories_hash when
    both present. `partial` is intentionally weaker: silence on unavailable
    fields is not "agreement".
    """
    if a.get("record_count") != b.get("record_count"):
        return False, "record_count differs"

    a_flav = a.get("flavour")
    b_flav = b.get("flavour")

    if a_flav == "full" and b_flav == "full":
        if a["content_hash"] != b["content_hash"]:
            return False, "content_hash differs (records edited)"
        return True, "content_hash matches"

    # At least one partial. Compare what both sides have.
    checked: list[str] = ["record_count"]

    a_latest = a.get("latest_id") or a.get("latest_timestamp")
    b_latest = b.get("latest_id") or b.get("latest_timestamp")
    if a_latest is not None and b_latest is not None:
        if a_latest != b_latest:
            return False, "latest identifier differs"
        checked.append("latest_id")

    a_cats = a.get("categories_hash")
    b_cats = b.get("categories_hash")
    if a_cats is not None and b_cats is not None:
        if a_cats != b_cats:
            return False, "categories_hash differs"
        checked.append("categories_hash")

    return True, f"partial agree on: {', '.join(checked)}"
