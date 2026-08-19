"""Registry loader: parses config/sources.yaml, validates cross-refs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class RegistryError(ValueError):
    """Raised on malformed registry (invalid YAML, dangling refs, etc)."""


@dataclass
class ObjectDef:
    name: str
    description: str
    identity_key: str
    expected_fields: dict[str, str] | None = None
    # Phase 2: name → type hint map (informational; name-only check in Phase 2A).
    # Compared against adapter-reported `source_payload_keys` (mcp_stdio only).
    # Absent / None → no contract check (backward compat with Phase 1 registries).


@dataclass
class SourceDef:
    name: str
    object: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)


@dataclass
class Registry:
    version: int
    objects: dict[str, ObjectDef]
    sources: list[SourceDef]

    def sources_for(self, object_name: str) -> list[SourceDef]:
        return [s for s in self.sources if s.object == object_name]

    def object_names(self) -> list[str]:
        return list(self.objects.keys())


def load_registry(path: str | Path) -> Registry:
    p = Path(path)
    if not p.exists():
        raise RegistryError(f"registry file not found: {p}")

    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise RegistryError(f"invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise RegistryError("top-level must be a mapping")

    version = data.get("version")
    if version != 1:
        raise RegistryError(f"unsupported registry version: {version!r} (expected 1)")

    raw_objects = data.get("objects") or {}
    if not isinstance(raw_objects, dict):
        raise RegistryError("'objects' must be a mapping")

    objects: dict[str, ObjectDef] = {}
    for name, spec in raw_objects.items():
        if not isinstance(spec, dict):
            raise RegistryError(f"object {name!r}: must be a mapping")
        raw_expected = spec.get("expected_fields")
        expected: dict[str, str] | None
        if raw_expected is None:
            expected = None
        elif isinstance(raw_expected, dict):
            expected = {str(k): str(v) for k, v in raw_expected.items()}
        else:
            raise RegistryError(
                f"object {name!r}: 'expected_fields' must be a mapping or omitted"
            )
        objects[name] = ObjectDef(
            name=name,
            description=spec.get("description", ""),
            identity_key=spec.get("identity_key", "id"),
            expected_fields=expected,
        )

    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        raise RegistryError("'sources' must be a list")

    sources: list[SourceDef] = []
    seen_names: set[str] = set()
    for spec in raw_sources:
        if not isinstance(spec, dict):
            raise RegistryError("each source must be a mapping")
        name = spec.get("name")
        if not name or not isinstance(name, str):
            raise RegistryError("source missing 'name'")
        if name in seen_names:
            raise RegistryError(f"duplicate source name: {name!r}")
        seen_names.add(name)

        obj = spec.get("object")
        if obj not in objects:
            raise RegistryError(
                f"source {name!r}: references undefined object {obj!r}"
            )

        kind = spec.get("kind")
        if not kind:
            raise RegistryError(f"source {name!r}: missing 'kind'")

        sources.append(
            SourceDef(
                name=name,
                object=obj,
                kind=kind,
                config=spec.get("config") or {},
                freshness=spec.get("freshness") or {},
            )
        )

    return Registry(version=version, objects=objects, sources=sources)


def git_head_info(repo_path: str | Path) -> dict[str, str | None]:
    """Return {git_head, git_head_date} for a repo, or Nones if unavailable.

    Never raises. Errors are captured to keep meta_list_sources robust.
    """
    repo = Path(repo_path)
    if not repo.exists():
        return {"git_head": None, "git_head_date": None, "git_error": "repo not found"}

    def _run(args: list[str]) -> str | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if r.returncode != 0:
                return None
            return r.stdout.strip() or None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    return {
        "git_head": _run(["rev-parse", "--short", "HEAD"]),
        "git_head_date": _run(["log", "-1", "--format=%cI"]),
        "git_error": None,
    }
