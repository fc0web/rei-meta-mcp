"""Fingerprint properties: order-independent, sensitive to real changes."""

from __future__ import annotations

from rei_meta_mcp.fingerprint import (
    compute_full_fingerprint,
    compute_partial_fingerprint,
    fingerprints_agree,
)


def test_full_identical():
    recs = [{"id": f"x-{i}", "body": f"b-{i}", "updated_at": f"2026-08-19T00:00:{i:02d}Z"} for i in range(10)]
    a = compute_full_fingerprint(recs)
    b = compute_full_fingerprint(recs)
    assert a == b


def test_full_order_independent():
    recs = [{"id": f"x-{i}", "body": f"b-{i}", "updated_at": None} for i in range(10)]
    a = compute_full_fingerprint(recs)
    b = compute_full_fingerprint(list(reversed(recs)))
    assert a["id_set_hash"] == b["id_set_hash"]
    assert a["content_hash"] == b["content_hash"]


def test_full_count_change_detected():
    a = compute_full_fingerprint([{"id": str(i), "body": ""} for i in range(10)])
    b = compute_full_fingerprint([{"id": str(i), "body": ""} for i in range(11)])
    assert a["record_count"] != b["record_count"]
    agree, reason = fingerprints_agree(a, b)
    assert not agree
    assert "record_count" in reason


def test_full_id_swap_detected():
    a = compute_full_fingerprint([{"id": str(i), "body": ""} for i in range(10)])
    swap = [{"id": str(i), "body": ""} for i in range(10)]
    swap[0]["id"] = "999"
    b = compute_full_fingerprint(swap)
    assert a["record_count"] == b["record_count"]
    assert a["id_set_hash"] != b["id_set_hash"]
    agree, reason = fingerprints_agree(a, b)
    assert not agree


def test_full_body_edit_detected():
    a = compute_full_fingerprint([{"id": str(i), "body": f"orig-{i}"} for i in range(10)])
    edited = [{"id": str(i), "body": f"orig-{i}"} for i in range(10)]
    edited[3]["body"] = "TAMPERED"
    b = compute_full_fingerprint(edited)
    assert a["record_count"] == b["record_count"]
    assert a["id_set_hash"] == b["id_set_hash"]
    assert a["content_hash"] != b["content_hash"]
    agree, reason = fingerprints_agree(a, b)
    assert not agree
    assert "content" in reason


def test_partial_count_only_still_flags_divergence():
    a = compute_partial_fingerprint(1677, latest_id="seed-1677", categories={"c1": 100})
    b = compute_partial_fingerprint(1675, latest_id="seed-1675", categories={"c1": 98})
    agree, reason = fingerprints_agree(a, b)
    assert not agree
    assert "record_count" in reason


def test_partial_full_mixed_agrees_when_available_fields_match():
    """A partial from mcp_stdio and a full from sqlite can be compared on
    the fields both expose. Same count + same latest = agree at the partial level."""
    full = compute_full_fingerprint(
        [{"id": f"seed-{i:04d}", "body": f"body-{i}", "updated_at": f"2026-08-19T00:00:{i:02d}Z"} for i in range(5)]
    )
    partial = compute_partial_fingerprint(5, latest_id=None)
    agree, _ = fingerprints_agree(full, partial)
    assert agree  # nothing to disagree on beyond count
