"""Adapter base class + shared result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class UnreachableError(RuntimeError):
    """Raised by adapters when the source cannot be probed.

    §4: this is NOT a coherent state. Callers must record it as `unreachable`.
    """


@dataclass
class ProbeResult:
    """Result of a single source probe.

    `records` is populated only when the adapter can enumerate everything
    (used to build a full fingerprint). Adapters that expose a status
    endpoint only should leave `records=None` and populate `summary`.
    """

    records: list[dict[str, Any]] | None = None
    summary: dict[str, Any] | None = None


class Adapter(ABC):
    """Base class for source adapters.

    Implementations should raise UnreachableError on any inability to probe
    (missing file, timeout, subprocess crash). They must NOT return an empty
    result to mean "unreachable" — the caller cannot distinguish that from
    a truly empty source.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def probe(self) -> ProbeResult:
        ...

    def close(self) -> None:  # noqa: B027 — optional hook
        pass
