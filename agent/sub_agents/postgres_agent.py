"""PostgreSQL specialist — Toolbox SQL execution is routed via :class:`~agent.tools_client.MCPToolsClient`."""

from __future__ import annotations

DATABASE_KEY = "postgresql"


def describe() -> str:
    return "PostgreSQL relational queries through MCP Toolbox (read-only SQL)."
