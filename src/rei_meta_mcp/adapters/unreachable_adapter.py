"""Explicit unreachable placeholder.

Used to register a source that we know we cannot probe yet (e.g. remote
deployed MCP behind claude.ai), so that the coherence report keeps
surfacing 'this source is not being checked'. §4 protocol.
"""

from __future__ import annotations

from rei_meta_mcp.adapters.base import Adapter, ProbeResult, UnreachableError


class UnreachablePlaceholderAdapter(Adapter):
    def probe(self) -> ProbeResult:
        reason = self.config.get("reason", "placeholder — probe not implemented")
        raise UnreachableError(reason)
