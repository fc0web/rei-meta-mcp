"""Source adapters. Each kind lives in its own module."""

from rei_meta_mcp.adapters.base import Adapter, ProbeResult, UnreachableError
from rei_meta_mcp.adapters.sqlite_adapter import SqliteAdapter
from rei_meta_mcp.adapters.mcp_stdio_adapter import McpStdioAdapter
from rei_meta_mcp.adapters.unreachable_adapter import UnreachablePlaceholderAdapter


def build_adapter(kind: str, config: dict) -> Adapter:
    if kind == "sqlite":
        return SqliteAdapter(config)
    if kind == "mcp_stdio":
        return McpStdioAdapter(config)
    if kind == "unreachable_placeholder":
        return UnreachablePlaceholderAdapter(config)
    raise ValueError(f"unknown adapter kind: {kind!r}")


__all__ = [
    "Adapter",
    "ProbeResult",
    "UnreachableError",
    "SqliteAdapter",
    "McpStdioAdapter",
    "UnreachablePlaceholderAdapter",
    "build_adapter",
]
