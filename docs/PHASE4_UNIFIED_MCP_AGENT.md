# Phase 4 — Agent wired to unified MCP

## What changed

- **`agent/tools_client.py`** (`MCPToolsClient`):
  - **Discovers tools** via **`GET /v1/tools` first** (FastAPI unified server). Falls back to **`POST /mcp` `tools/list`** (Microsoft Toolbox) if needed.
  - **Executes** via **`POST /v1/tools/{tool_name}`** with JSON `{"sql": "..."}` or `{"pipeline": "[...]"}` when `_mcp_api == "unified"`.
  - **Schema**: **`GET /schema/{tool_name}`** per tool, merged with bootstrap probes.
- **`mcp/db_config.py`**: added **`query_postgres_oracleforge`** → database **`oracleforge`** (Yelp Postgres seed used by this repo).

## Runtime

1. Start DBs + **`mcp-server`** (see `mcp/docker-compose.yml` and `scripts/mcp_up.ps1`).
2. Ensure **`MCP_BASE_URL=http://localhost:5000`** (default) so the agent hits the unified server.

## Legacy Toolbox

If **`GET /v1/tools`** fails and **`/mcp`** responds, the client sets **`_mcp_api = "toolbox"`** (unchanged JSON-RPC path).
