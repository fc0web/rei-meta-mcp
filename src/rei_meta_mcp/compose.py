"""meta_compose — Phase 1 shape only.

Registry can declare `output_schema` / `input_schema` as opaque strings
on each source; compose checks whether they match. Real schema inference
is Phase 3 or later.
"""

from __future__ import annotations

from typing import Any

from rei_meta_mcp.registry import Registry


def check_compose(
    registry: Registry,
    from_source: str,
    to_source: str,
) -> dict[str, Any]:
    src_map = {s.name: s for s in registry.sources}
    if from_source not in src_map:
        return {
            "composable": False,
            "from": {"name": from_source, "output_schema": None},
            "to": {"name": to_source, "input_schema": None},
            "reason": f"unknown source: {from_source!r}",
            "adapter_needed": None,
        }
    if to_source not in src_map:
        return {
            "composable": False,
            "from": {"name": from_source, "output_schema": None},
            "to": {"name": to_source, "input_schema": None},
            "reason": f"unknown source: {to_source!r}",
            "adapter_needed": None,
        }

    src = src_map[from_source]
    dst = src_map[to_source]

    out_schema = src.config.get("output_schema")
    in_schema = dst.config.get("input_schema")

    if out_schema is None or in_schema is None:
        return {
            "composable": False,
            "from": {"name": src.name, "output_schema": out_schema},
            "to": {"name": dst.name, "input_schema": in_schema},
            "reason": (
                "output_schema or input_schema not declared in registry; "
                "Phase 1 does not infer schemas"
            ),
            "adapter_needed": None,
        }

    if out_schema == in_schema:
        return {
            "composable": True,
            "from": {"name": src.name, "output_schema": out_schema},
            "to": {"name": dst.name, "input_schema": in_schema},
            "reason": "schemas match verbatim",
            "adapter_needed": None,
        }

    return {
        "composable": False,
        "from": {"name": src.name, "output_schema": out_schema},
        "to": {"name": dst.name, "input_schema": in_schema},
        "reason": "schema strings differ",
        "adapter_needed": f"{out_schema} -> {in_schema}",
    }
