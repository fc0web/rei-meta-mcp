"""Live smoke test against real Rei stack sources.

Run: PYTHONPATH=src python scripts/smoke_live.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from the repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rei_meta_mcp.coherence import check_coherence  # noqa: E402
from rei_meta_mcp.registry import load_registry  # noqa: E402
from rei_meta_mcp.server import _list_sources_impl  # noqa: E402


def main() -> int:
    reg_path = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
    reg = load_registry(reg_path)

    print("=" * 60)
    print("meta_list_sources()")
    print("=" * 60)
    print(json.dumps(_list_sources_impl(reg), indent=2, ensure_ascii=False))

    print()
    print("=" * 60)
    print('meta_check_coherence("seed_kernel")')
    print("=" * 60)
    report = check_coherence(reg, "seed_kernel", detail=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))

    print()
    print(f"VERDICT: {report['status']}")
    if report["divergence"]:
        for line in report["divergence"]["disagreements"]:
            print(f"  - {line}")
    for w in report["warnings"]:
        print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
