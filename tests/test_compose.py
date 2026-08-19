"""meta_compose — Phase 1 declarative shape match."""

from __future__ import annotations

from rei_meta_mcp.compose import check_compose
from rei_meta_mcp.registry import load_registry


def _reg_with(a_out, b_in, make_registry):
    yaml = f"""
version: 1
objects:
  o:
    description: x
    identity_key: id
sources:
  - name: A
    object: o
    kind: sqlite
    config:
      path: /dev/null
      output_schema: "{a_out}"
  - name: B
    object: o
    kind: sqlite
    config:
      path: /dev/null
      input_schema: "{b_in}"
"""
    return load_registry(make_registry(yaml))


def test_composable_when_schemas_match(make_registry):
    reg = _reg_with("Theory[]", "Theory[]", make_registry)
    r = check_compose(reg, "A", "B")
    assert r["composable"] is True


def test_not_composable_when_schemas_differ(make_registry):
    reg = _reg_with("Theory[]", "Measurement[]", make_registry)
    r = check_compose(reg, "A", "B")
    assert r["composable"] is False
    assert r["adapter_needed"] == "Theory[] -> Measurement[]"


def test_not_composable_when_schema_not_declared(make_registry):
    yaml = """
version: 1
objects:
  o:
    description: x
    identity_key: id
sources:
  - name: A
    object: o
    kind: sqlite
    config: {path: /dev/null}
  - name: B
    object: o
    kind: sqlite
    config: {path: /dev/null}
"""
    reg = load_registry(make_registry(yaml))
    r = check_compose(reg, "A", "B")
    assert r["composable"] is False
    assert "not declared" in r["reason"]


def test_unknown_source(make_registry):
    reg = _reg_with("X", "X", make_registry)
    r = check_compose(reg, "ghost", "B")
    assert r["composable"] is False
    assert "unknown source" in r["reason"]
