"""Local MCP stub – used only when the real 'mcp' package is unavailable.

Place this file at src/mcp/__init__.py so Python finds it on PYTHONPATH=src
before looking in site-packages.  The real mcp package (mcp>=1.9.0) must be
installed for production / CI.  This stub exposes just enough surface area to
let unit and property tests import cerebra.mcp_server without crashing.

DO NOT use this in production.  Remove it once mcp is pip-installable on this
machine.
"""
from __future__ import annotations

from typing import Any, Callable


# ── mcp.types ────────────────────────────────────────────────────────────────

class TextContent:
    def __init__(self, *, type: str, text: str) -> None:
        self.type = type
        self.text = text


class Tool:
    def __init__(self, *, name: str, description: str, inputSchema: dict) -> None:
        self.name = name
        self.description = description
        self.inputSchema = inputSchema


class Resource:
    def __init__(self, *, uri: str, name: str, description: str, mimeType: str) -> None:
        self.uri = uri
        self.name = name
        self.description = description
        self.mimeType = mimeType


# ── mcp.server ────────────────────────────────────────────────────────────────

class Server:
    """Minimal stub of mcp.server.Server."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._list_tools_handler: Callable | None = None
        self._call_tool_handler: Callable | None = None
        self._list_resources_handler: Callable | None = None
        self._read_resource_handler: Callable | None = None

    def list_tools(self) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._list_tools_handler = fn
            return fn
        return decorator

    def call_tool(self) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._call_tool_handler = fn
            return fn
        return decorator

    def list_resources(self) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._list_resources_handler = fn
            return fn
        return decorator

    def read_resource(self) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._read_resource_handler = fn
            return fn
        return decorator

    def create_initialization_options(self) -> dict:
        return {}

    async def run(self, read_stream: Any, write_stream: Any, options: Any) -> None:
        pass  # no-op in stub


# ── mcp.server.stdio ──────────────────────────────────────────────────────────

from contextlib import asynccontextmanager


@asynccontextmanager  # type: ignore[arg-type]
async def stdio_server():
    """Stub context manager — yields (None, None) for testing."""
    yield (None, None)


# Patch sub-module structure so 'from mcp.server.stdio import stdio_server' works
import sys
import types

_server_mod = types.ModuleType("mcp.server")
_server_mod.Server = Server  # type: ignore[attr-defined]

_stdio_mod = types.ModuleType("mcp.server.stdio")
_stdio_mod.stdio_server = stdio_server  # type: ignore[attr-defined]

_types_mod = types.ModuleType("mcp.types")
_types_mod.TextContent = TextContent  # type: ignore[attr-defined]
_types_mod.Tool = Tool  # type: ignore[attr-defined]
_types_mod.Resource = Resource  # type: ignore[attr-defined]

sys.modules.setdefault("mcp.server", _server_mod)
sys.modules.setdefault("mcp.server.stdio", _stdio_mod)
sys.modules.setdefault("mcp.types", _types_mod)
