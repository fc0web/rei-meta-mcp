"""Coherence + CHECKER dashboard — read-only side-by-side view.

Renders:
  - CHECKER (rei-checker-mcp): `python -m rei_checker stats` (subprocess, JSON stdout)
  - META   (rei-meta-mcp):    check_coherence() via direct import (same package)

Failures on one side never suppress the other (fingerprints_agree-style silence).

Config (env vars):
  REI_CHECKER_MODULE_DIR   — path to rei-checker-mcp checkout (required for CHECKER side)
  REI_CHECKER_LEDGER       — passed through to the checker subprocess (optional)
  REI_META_MCP_REGISTRY    — sources.yaml path (default: <cwd>/config/sources.yaml)
  REI_DASHBOARD_OBJECT     — coherence object name (default: seed_kernel)

CLI (installed as `rei-meta-dashboard` via [project.scripts]):
  rei-meta-dashboard                    # uses REI_DASHBOARD_OBJECT or "seed_kernel"
  rei-meta-dashboard seed_kernel        # explicit object name

Exit codes:
  0 — at least one side produced a report
  1 — both sides unavailable
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from .coherence import check_coherence
from .registry import RegistryError, load_registry


DEFAULT_OBJECT = "seed_kernel"
CHECKER_TIMEOUT_SEC = 30


def read_checker_stats() -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Invoke `python -m rei_checker stats`; return (parsed_json, error_msg).

    CHECKER lives in a separate repo (rei-checker-mcp), so we spawn its CLI
    rather than importing. `sys.executable -m rei_checker` — same Python venv.
    """
    module_dir = os.environ.get("REI_CHECKER_MODULE_DIR")
    if not module_dir:
        return None, "REI_CHECKER_MODULE_DIR not set"
    checker_root = Path(module_dir)
    if not checker_root.exists():
        return None, f"REI_CHECKER_MODULE_DIR does not exist: {checker_root}"

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "rei_checker", "stats"],
            cwd=str(checker_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CHECKER_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None, f"checker stats timed out after {CHECKER_TIMEOUT_SEC}s"
    except FileNotFoundError as e:
        return None, f"python not found: {e}"

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip() or "(no stderr)"
        return None, f"checker exited {proc.returncode}: {stderr}"

    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, f"checker returned non-JSON: {e}"


def read_meta_coherence(
    object_name: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Load registry and call check_coherence(); return (report, error_msg).

    META side is in-package: no sys.path manipulation, no dynamic import.
    """
    registry_path = os.environ.get("REI_META_MCP_REGISTRY") or str(
        Path.cwd() / "config" / "sources.yaml"
    )
    if not Path(registry_path).exists():
        return None, f"registry not found: {registry_path}"

    try:
        reg = load_registry(registry_path)
    except RegistryError as e:
        return None, f"registry parse failed: {e}"

    if object_name not in reg.objects:
        available = ", ".join(reg.object_names()) or "(empty)"
        return None, f"object {object_name!r} not in registry; available: {available}"

    try:
        report = check_coherence(reg, object_name, detail=False)
    except Exception as e:
        return None, f"check_coherence raised {type(e).__name__}: {e}"

    return report, None


def format_checker(stats: dict[str, Any]) -> list[str]:
    lines: list[str] = ["[CHECKER]"]
    total = int(stats.get("total", 0))
    valid = int(stats.get("valid", 0))
    invalid = int(stats.get("invalid", 0))
    undecided = int(stats.get("undecided", 0))
    rate = float(stats.get("decision_rate", 0.0))

    lines.append(f"  decision_rate: {rate:.1%}  ({valid + invalid}/{total})")
    lines.append(f"  valid:         {valid}")
    lines.append(f"  invalid:       {invalid}")
    lines.append(f"  undecided:     {undecided}")

    breakdown = stats.get("reason_breakdown") or {}
    if breakdown:
        top_reason, top_count = max(breakdown.items(), key=lambda kv: kv[1])
        lines.append(f"  top reason:    {top_reason} (x{top_count})")
        lines.append("  reason_breakdown:")
        for k in sorted(breakdown.keys()):
            lines.append(f"    - {k}: {breakdown[k]}")
    else:
        lines.append("  reason_breakdown: (empty)")

    d8 = stats.get("d_fumt8_breakdown")
    if d8:
        lines.append("  d_fumt8_breakdown:")
        for k in sorted(d8.keys()):
            lines.append(f"    - {k}: {d8[k]}")

    return lines


def format_meta(report: dict[str, Any], object_name: str) -> list[str]:
    lines: list[str] = ["[META]"]
    lines.append(f"  object:        {object_name}")
    lines.append(f"  status:        {report.get('status', '?')}")
    lines.append(f"  checked_at:    {report.get('checked_at', '?')}")

    sources = report.get("sources") or []
    reachable = sum(1 for s in sources if s.get("reachable"))
    unreachable = len(sources) - reachable
    lines.append(
        f"  sources:       {len(sources)} ({reachable} reachable, {unreachable} unreachable)"
    )
    for s in sources:
        mark = "OK" if s.get("reachable") else "!!"
        name = s.get("name", "?")
        kind = s.get("kind", "?")
        suffix = ""
        if not s.get("reachable") and s.get("error"):
            suffix = f" — {s['error']}"
        lines.append(f"    [{mark}] {name} ({kind}){suffix}")

    warnings = report.get("warnings") or []
    if warnings:
        lines.append(f"  warnings ({len(warnings)}):")
        for w in warnings:
            lines.append(f"    - {w}")
    else:
        lines.append("  warnings:      (none)")

    divergence = report.get("divergence")
    if divergence:
        lines.append("  divergence:")
        for key in ("count_diff", "latest_id_diff", "latest_timestamp_diff"):
            value = divergence.get(key)
            if value:
                lines.append(f"    {key}: {value}")
        disagreements = divergence.get("disagreements") or []
        for d in disagreements:
            lines.append(f"    - {d}")

    return lines


def format_error(name: str, err: str) -> list[str]:
    return [f"[{name}]", f"  UNAVAILABLE: {err}"]


def render_side_by_side(
    left: list[str], right: list[str], left_width: int = 44
) -> str:
    max_rows = max(len(left), len(right))
    left = left + [""] * (max_rows - len(left))
    right = right + [""] * (max_rows - len(right))
    out: list[str] = []
    for lrow, rrow in zip(left, right):
        out.append(f"{lrow:<{left_width}}  {rrow}")
    return "\n".join(out)


def run(object_name: str) -> int:
    checker_stats, checker_err = read_checker_stats()
    meta_report, meta_err = read_meta_coherence(object_name)

    left = (
        format_checker(checker_stats)
        if checker_stats is not None
        else format_error("CHECKER", checker_err or "(unknown error)")
    )
    right = (
        format_meta(meta_report, object_name)
        if meta_report is not None
        else format_error("META", meta_err or "(unknown error)")
    )

    print(render_side_by_side(left, right))

    if checker_stats is None and meta_report is None:
        return 1
    return 0


def main() -> int:
    """Entry point for `rei-meta-dashboard` script."""
    object_name = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("REI_DASHBOARD_OBJECT", DEFAULT_OBJECT)
    )
    return run(object_name)


if __name__ == "__main__":
    sys.exit(main())
