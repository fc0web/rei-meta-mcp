"""MCP stdio adapter — spawns a subprocess and speaks MCP protocol.

Used for `rei-aios-local-mcp`: probes the local `node dist/mcp/start-mcp.js`
build by calling its `get_kernel_status` tool. The response contains
`totalTheories`, `latestTheoryId`, and category counts — enough for a
partial fingerprint (§ fingerprint.compute_partial_fingerprint).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rei_meta_mcp.adapters.base import Adapter, ProbeResult, UnreachableError


class McpStdioAdapter(Adapter):
    def probe(self) -> ProbeResult:
        cfg = self.config
        command = cfg.get("command")
        if not command:
            raise UnreachableError("mcp_stdio config missing 'command'")
        args = list(cfg.get("args") or [])
        tool = cfg.get("tool", "get_kernel_status")
        tool_args = dict(cfg.get("tool_args") or {})
        timeout = float(cfg.get("timeout_sec", 30))

        try:
            payload = asyncio.run(
                _call_tool_once(command, args, tool, tool_args, timeout)
            )
        except UnreachableError:
            raise
        except asyncio.TimeoutError as e:
            raise UnreachableError(f"mcp_stdio probe timed out after {timeout}s") from e
        except Exception as e:
            raise UnreachableError(
                f"mcp_stdio probe failed: {type(e).__name__}: {e}"
            ) from e

        summary = _extract_status_summary(payload)
        return ProbeResult(summary=summary)


async def _call_tool_once(
    command: str,
    args: list[str],
    tool: str,
    tool_args: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Spawn the MCP server, call one tool, return decoded JSON payload."""
    params = StdioServerParameters(command=command, args=args, env=None)

    async def _run() -> dict[str, Any]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, tool_args)
                # result.content is a list of content parts; first is TextContent
                if not result.content:
                    raise UnreachableError(
                        f"tool {tool!r} returned no content"
                    )
                first = result.content[0]
                text = getattr(first, "text", None)
                if text is None:
                    raise UnreachableError(
                        f"tool {tool!r} returned non-text content: {type(first).__name__}"
                    )
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    raise UnreachableError(
                        f"tool {tool!r} returned non-JSON text: {e}"
                    ) from e

    return await asyncio.wait_for(_run(), timeout=timeout)


def _extract_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a status-tool response to fingerprint-ready fields.

    Handles both:
      - get_kernel_status: {totalTheories, latestTheoryId, categories}
      - search_theories with empty query: {total, ...}
    """
    if "totalTheories" in payload:
        return {
            "record_count": int(payload["totalTheories"]),
            "latest_id": payload.get("latestTheoryId"),
            "categories": _normalize_categories(payload.get("categories")),
            "source_payload_keys": sorted(payload.keys()),
        }
    if "total" in payload:
        return {
            "record_count": int(payload["total"]),
            "latest_id": None,
            "categories": None,
            "source_payload_keys": sorted(payload.keys()),
        }
    raise UnreachableError(
        f"unrecognized status payload keys: {sorted(payload.keys())}"
    )


def _normalize_categories(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): int(v) for k, v in value.items()}
    if isinstance(value, list):
        out: dict[str, int] = {}
        for entry in value:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("category")
                count = entry.get("count")
                if name is not None and count is not None:
                    out[str(name)] = int(count)
        return out or None
    return None
