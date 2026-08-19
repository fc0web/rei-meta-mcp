"""FastMCP server entry point. Three tools: list_sources, check_coherence, compose."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from rei_meta_mcp.adapters import build_adapter
from rei_meta_mcp.adapters.base import UnreachableError
from rei_meta_mcp.coherence import check_coherence
from rei_meta_mcp.compose import check_compose
from rei_meta_mcp.registry import Registry, git_head_info, load_registry


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


def _resolve_registry_path() -> Path:
    env = os.environ.get("REI_META_MCP_REGISTRY")
    return Path(env) if env else _default_registry_path()


def _list_sources_impl(
    registry: Registry,
    object_name: str | None = None,
) -> dict[str, Any]:
    """Enumerate registered sources with current reachability and freshness."""
    objects_out = []
    for obj_name, obj in registry.objects.items():
        if object_name is not None and obj_name != object_name:
            continue
        sources_out = []
        for src in registry.sources_for(obj_name):
            probe_info = _light_probe(src)
            freshness = {}
            repo = src.freshness.get("git_repo")
            if repo:
                freshness = git_head_info(repo)
            sources_out.append({
                "name": src.name,
                "kind": src.kind,
                "reachable": probe_info["reachable"],
                "record_count": probe_info["record_count"],
                "latest_id": probe_info["latest_id"],
                "git_head": freshness.get("git_head"),
                "git_head_date": freshness.get("git_head_date"),
                "error": probe_info["error"],
            })
        objects_out.append({
            "name": obj_name,
            "description": obj.description,
            "identity_key": obj.identity_key,
            "sources": sources_out,
        })
    return {"objects": objects_out}


def _light_probe(source) -> dict[str, Any]:
    """Best-effort probe returning only count + latest_id (no full fingerprint)."""
    try:
        adapter = build_adapter(source.kind, source.config)
        result = adapter.probe()
        adapter.close()
    except UnreachableError as e:
        return {
            "reachable": False,
            "record_count": None,
            "latest_id": None,
            "error": str(e),
        }
    except Exception as e:
        return {
            "reachable": False,
            "record_count": None,
            "latest_id": None,
            "error": f"{type(e).__name__}: {e}",
        }

    if result.records is not None:
        count = len(result.records)
        # 'latest' derived from the record with the largest updated_at, if any
        latest_id: str | None = None
        latest_ts: str | None = None
        for r in result.records:
            ts = r.get("updated_at")
            if ts is None:
                continue
            if latest_ts is None or str(ts) > latest_ts:
                latest_ts = str(ts)
                latest_id = str(r.get("id"))
        return {
            "reachable": True,
            "record_count": count,
            "latest_id": latest_id,
            "error": None,
        }
    if result.summary is not None:
        return {
            "reachable": True,
            "record_count": result.summary.get("record_count"),
            "latest_id": result.summary.get("latest_id"),
            "error": None,
        }
    return {
        "reachable": False,
        "record_count": None,
        "latest_id": None,
        "error": "adapter returned neither records nor summary",
    }


def build_mcp(registry_path: Path | None = None) -> MCPServer:
    """Construct the MCP server. Registry is loaded lazily per-call
    so that edits to sources.yaml take effect without restarting."""
    registry_path = registry_path or _resolve_registry_path()
    mcp = MCPServer(name="rei-meta-mcp", version="0.1.0-alpha")

    def _load() -> Registry:
        return load_registry(registry_path)

    @mcp.tool()
    def meta_list_sources(object_name: str | None = None) -> dict[str, Any]:
        """List registered sources with current reachability and freshness."""
        return _list_sources_impl(_load(), object_name)

    @mcp.tool()
    def meta_check_coherence(
        object_name: str,
        detail: bool = False,
    ) -> dict[str, Any]:
        """Check whether all sources for `object_name` agree.

        Verdicts: coherent | divergent | unreachable | single_source.
        §4: unreachable/single_source are warnings, not silent success.
        """
        return check_coherence(_load(), object_name, detail=detail)

    @mcp.tool()
    def meta_compose(from_source: str, to_source: str) -> dict[str, Any]:
        """Check whether the output of `from_source` can feed `to_source`.

        Phase 1: declarative schema string match only.
        """
        return check_compose(_load(), from_source, to_source)

    return mcp


def main() -> None:
    mcp = build_mcp()
    mcp.run()


if __name__ == "__main__":
    main()
