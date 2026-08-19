#!/usr/bin/env python3
"""Standalone launcher for rei-meta-mcp — no PYTHONPATH env required.

Claude Desktop (Windows Store UWP sandbox) does not reliably propagate
custom env vars to child processes. This launcher bootstraps sys.path
and REI_META_MCP_REGISTRY from the script's own filesystem location, so
the Desktop config can be a direct file invocation with `env: {}`.

Usage from Claude Desktop config (matches rei-memory-mcp pattern):

    "rei-meta": {
      "command": "C:/path/to/python.exe",
      "args": ["-u", "C:/path/to/rei-meta-mcp/run_server.py"],
      "env": {}
    }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Make src/ importable without install or PYTHONPATH
sys.path.insert(0, str(_HERE / "src"))

# Default registry location relative to launcher; caller may override via env.
os.environ.setdefault(
    "REI_META_MCP_REGISTRY", str(_HERE / "config" / "sources.yaml")
)

from rei_meta_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
