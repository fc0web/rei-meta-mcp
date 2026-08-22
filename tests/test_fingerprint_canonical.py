"""fingerprint_canonical regression + determinism tests.

Origin: 2026-08-22 bug — meta_check_coherence('seed_kernel', detail=True)
returned `divergent` for a full × partial source pair even when
record_count matched, because fingerprints_agree coerced latest_id and
latest_timestamp into one slot via `a.get('latest_id') or a.get('latest_timestamp')`
and compared an ISO-8601 datetime string against an arbitrary id string.

Fix: fingerprint_canonical(fp) exposes typed fields separately;
fingerprints_agree compares them in their own slots only.

Scope: this file locks in fingerprint_canonical + fingerprints_agree.
It does NOT test theory_canonical(T) — that function is out of scope.
"""

from __future__ import annotations

from rei_meta_mcp.fingerprint import (
    compute_full_fingerprint,
    compute_partial_fingerprint,
    fingerprint_canonical,
    fingerprints_agree,
    serialize_fingerprint_canonical,
)


# --- Determinism floor ------------------------------------------------------

def test_canonical_deterministic_full():
    """Floor: same input → byte-equal canonical serialization on two runs."""
    recs = [
        {"id": f"seed-{i:04d}", "body": f"body-{i}", "updated_at": f"2026-08-19T00:00:{i:02d}Z"}
        for i in range(20)
    ]
    fp = compute_full_fingerprint(recs)
    bytes_a = serialize_fingerprint_canonical(fp)
    bytes_b = serialize_fingerprint_canonical(fp)
    assert bytes_a == bytes_b
    # And a re-computed fingerprint of the same records must canonicalize to
    # the same bytes.
    fp2 = compute_full_fingerprint(recs)
    assert serialize_fingerprint_canonical(fp2) == bytes_a


def test_canonical_deterministic_partial():
    """Floor: same input → byte-equal for partial flavour too."""
    fp = compute_partial_fingerprint(1677, latest_id="resilient-knowledge-recovery", categories={"logic": 42, "geometry": 13})
    a = serialize_fingerprint_canonical(fp)
    b = serialize_fingerprint_canonical(fp)
    assert a == b


def test_canonical_idempotent():
    """Canonicalizing a canonical view returns bytes equal to canonicalizing the raw."""
    fp = compute_full_fingerprint([{"id": "x", "body": "y", "updated_at": "2026-08-22T00:00:00Z"}])
    once = fingerprint_canonical(fp)
    twice = fingerprint_canonical(once)
    # `once` is already the canonical shape; running canonical again over it
    # must yield the same dict (idempotent under the canonical operation).
    assert twice == once
    assert serialize_fingerprint_canonical(once) == serialize_fingerprint_canonical(fp)


# --- Type separation --------------------------------------------------------

def test_canonical_full_exposes_only_full_fields():
    fp = compute_full_fingerprint([{"id": "x", "body": "y", "updated_at": "2026-08-22T00:00:00Z"}])
    c = fingerprint_canonical(fp)
    assert c["flavour"] == "full"
    assert c["record_count"] == 1
    assert c["latest_timestamp"] == "2026-08-22T00:00:00Z"
    assert c["content_hash"] is not None
    assert c["id_set_hash"] is not None
    # partial-only fields must be None on a full fingerprint
    assert c["latest_id"] is None
    assert c["categories_hash"] is None


def test_canonical_partial_exposes_only_partial_fields():
    fp = compute_partial_fingerprint(1677, latest_id="resilient-knowledge-recovery")
    c = fingerprint_canonical(fp)
    assert c["flavour"] == "partial"
    assert c["record_count"] == 1677
    assert c["latest_id"] == "resilient-knowledge-recovery"
    # full-only fields must be None on a partial fingerprint
    assert c["latest_timestamp"] is None
    assert c["content_hash"] is None
    assert c["id_set_hash"] is None


# --- 2026-08-22 bug reproducer ---------------------------------------------

def test_2026_08_22_bug_full_x_partial_matching_count_agrees():
    """The exact shape that surfaced the bug on 2026-08-22.

    - Source A (sqlite → full): 1677 records, latest_timestamp = '2026-08-19T00:00:00Z'
    - Source B (mcp_stdio → partial): 1677 records, latest_id = 'resilient-knowledge-recovery'
    - record_count matches.

    Pre-fix: fingerprints_agree returned (False, 'latest identifier differs')
             because `latest_id or latest_timestamp` coerced two type-different
             strings into one slot and compared them with !=.

    Post-fix: cross-flavour comparison has nothing type-uniform beyond
              record_count. Returns (True, 'agree on: record_count').
              A partial source cannot prove full-side content unchanged —
              that requires upgrading the adapter, not tighter comparison.
    """
    # simulate the two live sources
    full = {
        "flavour": "full",
        "record_count": 1677,
        "id_set_hash": "deadbeef",
        "content_hash": "cafef00d",
        "latest_timestamp": "2026-08-19T00:00:00Z",
    }
    partial = {
        "flavour": "partial",
        "record_count": 1677,
        "latest_id": "resilient-knowledge-recovery",
        "categories_hash": None,
    }
    agree, reason = fingerprints_agree(full, partial)
    assert agree, (
        f"cross-flavour with matching count must not be flagged divergent "
        f"purely because latest_id and latest_timestamp are different strings. "
        f"got reason={reason!r}"
    )
    assert "record_count" in reason


def test_2026_08_22_bug_reverse_order_also_agrees():
    """Order-independence: swapping a and b must give the same verdict."""
    full = {
        "flavour": "full", "record_count": 1677,
        "id_set_hash": "x", "content_hash": "y", "latest_timestamp": "2026-08-19T00:00:00Z",
    }
    partial = {
        "flavour": "partial", "record_count": 1677,
        "latest_id": "resilient-knowledge-recovery", "categories_hash": None,
    }
    a1, r1 = fingerprints_agree(full, partial)
    a2, r2 = fingerprints_agree(partial, full)
    assert a1 == a2
    # reason strings may differ in field ordering but must not disagree
    assert a1 is True


def test_cross_flavour_count_mismatch_still_divergent():
    """Regression guard: the 2026-08-19 incident shape (1677 vs 1675)
    must still be detected. The fix must not paper over real drift."""
    full = {
        "flavour": "full", "record_count": 1677,
        "id_set_hash": "x", "content_hash": "y", "latest_timestamp": "2026-08-19T00:00:00Z",
    }
    partial = {
        "flavour": "partial", "record_count": 1675,
        "latest_id": "some-earlier-id", "categories_hash": None,
    }
    agree, reason = fingerprints_agree(full, partial)
    assert not agree
    assert "record_count" in reason


# --- Partial × partial: full latest_id semantics preserved -----------------

def test_partial_x_partial_latest_id_still_compared():
    """When both sides are partial, latest_id IS compared (real signal)."""
    a = compute_partial_fingerprint(1677, latest_id="seed-a")
    b = compute_partial_fingerprint(1677, latest_id="seed-b")
    agree, reason = fingerprints_agree(a, b)
    assert not agree
    assert "latest_id" in reason


def test_partial_x_partial_matching_latest_id_agrees():
    a = compute_partial_fingerprint(1677, latest_id="same-id")
    b = compute_partial_fingerprint(1677, latest_id="same-id")
    agree, reason = fingerprints_agree(a, b)
    assert agree
    assert "latest_id" in reason


# --- Full × full: latest_timestamp still compared --------------------------

def test_full_x_full_content_hash_authoritative():
    """Full × full uses content_hash (strongest); a mismatch is divergent
    even if counts and id sets match (body edit case). This preserves the
    original semantics."""
    a = compute_full_fingerprint([{"id": "x", "body": "orig", "updated_at": "2026-08-22T00:00:00Z"}])
    b = compute_full_fingerprint([{"id": "x", "body": "edited", "updated_at": "2026-08-22T00:00:00Z"}])
    agree, reason = fingerprints_agree(a, b)
    assert not agree
    assert "content_hash" in reason
