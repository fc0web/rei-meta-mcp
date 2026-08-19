"""Shared fixtures.

We build in-process SQLite files under a fresh temp dir per test session
so tests never touch real project data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_theories_db(path: Path, ids: list[str], body_of=None) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE theories (
            id TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    body_fn = body_of or (lambda i: f"body-of-{i}")
    conn.executemany(
        "INSERT INTO theories (id, body, updated_at) VALUES (?, ?, ?)",
        [(i, body_fn(i), f"2026-08-19T00:00:{n:02d}Z") for n, i in enumerate(ids)],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def two_db_identical(tmp_path):
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    ids = [f"t-{i:04d}" for i in range(100)]
    _make_theories_db(a, ids)
    _make_theories_db(b, ids)
    return a, b


@pytest.fixture
def two_db_count_diff(tmp_path):
    """1677 vs 1675 — the 2026-08-19 incident shape."""
    a = tmp_path / "local.db"
    b = tmp_path / "stale.db"
    ids_a = [f"seed-{i:05d}" for i in range(1677)]
    ids_b = [f"seed-{i:05d}" for i in range(1675)]  # missing the last 2
    _make_theories_db(a, ids_a)
    _make_theories_db(b, ids_b)
    return a, b


@pytest.fixture
def two_db_same_count_diff_ids(tmp_path):
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    ids_a = [f"t-{i:04d}" for i in range(50)]
    ids_b = [f"t-{i:04d}" for i in range(50)]
    ids_b[0] = "t-999"  # one swap → same count, different ID sets
    _make_theories_db(a, ids_a)
    _make_theories_db(b, ids_b)
    return a, b


@pytest.fixture
def two_db_same_ids_diff_body(tmp_path):
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    ids = [f"t-{i:04d}" for i in range(50)]
    _make_theories_db(a, ids, body_of=lambda i: f"body-A-{i}")
    _make_theories_db(b, ids, body_of=lambda i: f"body-A-{i}" if i != "t-0025" else "body-B-edited")
    return a, b


def _write_registry(tmp_path: Path, sources_yaml: str) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    reg = cfg_dir / "sources.yaml"
    reg.write_text(sources_yaml, encoding="utf-8")
    return reg


@pytest.fixture
def make_registry(tmp_path):
    def _factory(yaml_text: str) -> Path:
        return _write_registry(tmp_path, yaml_text)
    return _factory
