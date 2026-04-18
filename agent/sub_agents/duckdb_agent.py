"""DuckDB specialist — analytical SQL (local file or Toolbox)."""

from __future__ import annotations

DATABASE_KEY = "duckdb"


def describe() -> str:
    return "DuckDB analytics SQL through MCP Toolbox or local DUCKDB_PATH."
