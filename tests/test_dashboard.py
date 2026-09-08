"""Unit tests for rei_meta_mcp.dashboard.

Pure-function coverage only (format_checker / format_meta / format_error /
render_side_by_side + main()'s object-name defaulting via env).
No env vars, no subprocess, no live sources needed.
"""

from __future__ import annotations

from rei_meta_mcp import dashboard


# ---------------------------------------------------------------- format_checker
def test_format_checker_basic():
    stats = {
        "total": 128,
        "valid": 71,
        "invalid": 22,
        "undecided": 35,
        "decision_rate": 0.727,
        "reason_breakdown": {
            "MISSING_AXIOM": 12,
            "PARSE_FAILURE": 2,
            "TIMEOUT": 8,
        },
    }
    lines = dashboard.format_checker(stats)
    assert lines[0] == "[CHECKER]"
    joined = "\n".join(lines)
    assert "decision_rate: 72.7%  (93/128)" in joined
    assert "valid:         71" in joined
    assert "invalid:       22" in joined
    assert "undecided:     35" in joined
    assert "top reason:    MISSING_AXIOM (x12)" in joined
    # keys should be sorted
    assert joined.index("MISSING_AXIOM") < joined.index("PARSE_FAILURE") < joined.index("TIMEOUT")


def test_format_checker_empty_breakdown():
    stats = {"total": 0, "valid": 0, "invalid": 0, "undecided": 0, "decision_rate": 0.0}
    lines = dashboard.format_checker(stats)
    joined = "\n".join(lines)
    assert "decision_rate: 0.0%" in joined
    assert "reason_breakdown: (empty)" in joined
    assert "top reason" not in joined


def test_format_checker_d_fumt8():
    stats = {
        "total": 10, "valid": 5, "invalid": 3, "undecided": 2, "decision_rate": 0.8,
        "d_fumt8_breakdown": {"T": 5, "F": 3, "U": 2},
    }
    lines = dashboard.format_checker(stats)
    joined = "\n".join(lines)
    assert "d_fumt8_breakdown:" in joined
    assert "- T: 5" in joined
    assert "- F: 3" in joined


# ---------------------------------------------------------------- format_meta
def test_format_meta_coherent():
    report = {
        "status": "coherent",
        "checked_at": "2026-08-25T02:14:33+00:00",
        "sources": [
            {"name": "rei-memory-local", "kind": "sqlite", "reachable": True},
            {"name": "rei-aios-local-mcp", "kind": "mcp_stdio", "reachable": True},
        ],
        "warnings": [],
    }
    lines = dashboard.format_meta(report, "seed_kernel")
    joined = "\n".join(lines)
    assert lines[0] == "[META]"
    assert "object:        seed_kernel" in joined
    assert "status:        coherent" in joined
    assert "sources:       2 (2 reachable, 0 unreachable)" in joined
    assert "[OK] rei-memory-local (sqlite)" in joined
    assert "[OK] rei-aios-local-mcp (mcp_stdio)" in joined
    assert "warnings:      (none)" in joined


def test_format_meta_divergent_with_unreachable():
    report = {
        "status": "divergent",
        "checked_at": "2026-08-25T03:00:00+00:00",
        "sources": [
            {"name": "s1", "kind": "sqlite", "reachable": True},
            {"name": "s2", "kind": "mcp_stdio", "reachable": True},
            {
                "name": "s3",
                "kind": "unreachable_placeholder",
                "reachable": False,
                "error": "not directly probeable",
            },
        ],
        "warnings": ["UNCHECKED: s3", "CONTRACT: s2 drift"],
        "divergence": {
            "count_diff": {"s1": 100, "s2": 99},
            "disagreements": ["s1 vs s2: record_count differs"],
        },
    }
    lines = dashboard.format_meta(report, "seed_kernel")
    joined = "\n".join(lines)
    assert "status:        divergent" in joined
    assert "sources:       3 (2 reachable, 1 unreachable)" in joined
    assert "[!!] s3 (unreachable_placeholder) — not directly probeable" in joined
    assert "warnings (2):" in joined
    assert "- UNCHECKED: s3" in joined
    assert "divergence:" in joined
    assert "count_diff: {'s1': 100, 's2': 99}" in joined
    assert "- s1 vs s2: record_count differs" in joined


def test_format_meta_no_divergence_block_when_missing():
    report = {
        "status": "coherent",
        "checked_at": "2026-08-25T03:00:00+00:00",
        "sources": [{"name": "s1", "kind": "sqlite", "reachable": True}],
        "warnings": [],
    }
    lines = dashboard.format_meta(report, "seed_kernel")
    assert "divergence:" not in "\n".join(lines)


# ---------------------------------------------------------------- format_error
def test_format_error():
    assert dashboard.format_error("CHECKER", "not set") == [
        "[CHECKER]",
        "  UNAVAILABLE: not set",
    ]


# ---------------------------------------------------------------- render_side_by_side
def test_render_side_by_side_equal_length():
    left = ["a", "b"]
    right = ["c", "d"]
    out = dashboard.render_side_by_side(left, right, left_width=6)
    lines = out.split("\n")
    assert len(lines) == 2
    # each line: left padded to width, two spaces, right
    assert lines[0] == "a       c"
    assert lines[1] == "b       d"


def test_render_side_by_side_pad_short_side():
    left = ["a", "b", "c"]
    right = ["x"]
    out = dashboard.render_side_by_side(left, right, left_width=4)
    lines = out.split("\n")
    assert len(lines) == 3
    # right pad kicks in on rows 2/3
    assert lines[0].startswith("a")
    assert lines[0].endswith("  x")
    assert lines[1].endswith("  ")  # right blank, trailing two spaces


def test_render_side_by_side_both_empty():
    assert dashboard.render_side_by_side([], []) == ""


# ---------------------------------------------------------------- main env defaulting
def test_main_defaults_to_seed_kernel_when_no_argv_no_env(monkeypatch):
    """When argv has no positional and REI_DASHBOARD_OBJECT is unset,
    dashboard should call run() with DEFAULT_OBJECT."""
    monkeypatch.delenv("REI_DASHBOARD_OBJECT", raising=False)
    monkeypatch.setattr(dashboard.sys, "argv", ["rei-meta-dashboard"])
    captured = {}

    def fake_run(name):
        captured["name"] = name
        return 42

    monkeypatch.setattr(dashboard, "run", fake_run)
    rc = dashboard.main()
    assert rc == 42
    assert captured["name"] == "seed_kernel"


def test_main_uses_argv_over_env(monkeypatch):
    monkeypatch.setenv("REI_DASHBOARD_OBJECT", "from_env")
    monkeypatch.setattr(dashboard.sys, "argv", ["rei-meta-dashboard", "from_argv"])
    captured = {}
    monkeypatch.setattr(dashboard, "run", lambda n: captured.setdefault("name", n) or 0)
    dashboard.main()
    assert captured["name"] == "from_argv"


def test_main_uses_env_when_no_argv(monkeypatch):
    monkeypatch.setenv("REI_DASHBOARD_OBJECT", "from_env")
    monkeypatch.setattr(dashboard.sys, "argv", ["rei-meta-dashboard"])
    captured = {}
    monkeypatch.setattr(dashboard, "run", lambda n: captured.setdefault("name", n) or 0)
    dashboard.main()
    assert captured["name"] == "from_env"


# ---------------------------------------------------------------- read_meta_coherence guards
def test_read_meta_coherence_missing_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("REI_META_MCP_REGISTRY", str(tmp_path / "does_not_exist.yaml"))
    report, err = dashboard.read_meta_coherence("seed_kernel")
    assert report is None
    assert err is not None
    assert "registry not found" in err
