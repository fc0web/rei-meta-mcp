"""SQLite adapter — reads a table directly."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rei_meta_mcp.adapters.base import Adapter, ProbeResult, UnreachableError


class SqliteAdapter(Adapter):
    def probe(self) -> ProbeResult:
        cfg = self.config
        path = cfg.get("path")
        if not path:
            raise UnreachableError("sqlite config missing 'path'")
        p = Path(path)
        if not p.exists():
            raise UnreachableError(f"sqlite file not found: {p}")

        table = cfg.get("table", "theories")
        id_col = cfg.get("id_column", "id")
        body_col = cfg.get("body_column", "body")
        updated_col = cfg.get("updated_at_column", "updated_at")

        try:
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f'SELECT "{id_col}" AS id, "{body_col}" AS body, '  # noqa: S608 — column names from trusted registry
                f'"{updated_col}" AS updated_at FROM "{table}"'
            )
            records = [dict(r) for r in cursor.fetchall()]
            conn.close()
        except sqlite3.Error as e:
            raise UnreachableError(f"sqlite probe failed: {e}") from e

        return ProbeResult(records=records)
