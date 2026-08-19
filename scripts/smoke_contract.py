"""Phase 2 live smoke test — contract mismatch surfacing.

Constructs a temporary registry that declares expected_fields matching
the finding #30 shape (rei-aios get_kernel_status description claims
'harmony_score' and 'seven_value_distribution', but the actual payload
returns only totalTheories/latestTheoryId/categories/dfumtValue).

Runs check_coherence against the real rei-aios-local-mcp subprocess.
Expects the CONTRACT warning to name both missing fields.

Live config/sources.yaml is NOT touched.

Run: python scripts/smoke_contract.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rei_meta_mcp.coherence import check_coherence  # noqa: E402
from rei_meta_mcp.registry import load_registry  # noqa: E402


TMP_REGISTRY_YAML = """
version: 1

objects:
  seed_kernel:
    description: "SEED_KERNEL 理論群 (Rei stack の中心対象)"
    identity_key: id
    expected_fields:
      totalTheories: int
      latestTheoryId: str
      categories: dict
      dfumtValue: scalar
      harmony_score: float
      seven_value_distribution: dict

sources:
  - name: rei-aios-local-mcp
    object: seed_kernel
    kind: mcp_stdio
    config:
      command: node
      args: ["C:/Users/user/rei-aios/dist/mcp/start-mcp.js"]
      cwd: "C:/Users/user/rei-aios"
      tool: get_kernel_status
      timeout_sec: 30
"""


def main() -> int:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(TMP_REGISTRY_YAML)
        tmp_path = Path(f.name)

    try:
        reg = load_registry(tmp_path)
        print("=" * 60)
        print('Phase 2 smoke: meta_check_coherence("seed_kernel")')
        print("=" * 60)
        report = check_coherence(reg, "seed_kernel")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print()
        print(f"VERDICT: {report['status']}")
        print()
        contract_warnings = [
            w for w in report["warnings"] if w.startswith("CONTRACT:")
        ]
        print(f"CONTRACT warnings: {len(contract_warnings)}")
        for w in contract_warnings:
            print(f"  ! {w}")

        # Phase 2 acceptance criteria
        assert contract_warnings, "expected at least one CONTRACT warning"
        joined = " ".join(contract_warnings)
        assert "harmony_score" in joined, "harmony_score should be flagged as missing"
        assert (
            "seven_value_distribution" in joined
        ), "seven_value_distribution should be flagged as missing"

        print()
        print("=" * 60)
        print("PHASE 2 SMOKE PASS — finding #30 shape mechanically detected")
        print("=" * 60)
        return 0
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
