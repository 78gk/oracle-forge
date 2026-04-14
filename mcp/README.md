# MCP Toolbox Setup

This project uses Google MCP Toolbox as the standard interface between the agent and DAB databases.

Canonical config file:
- `mcp/tools.yaml`

Canonical runtime stack:
- `mcp/docker-compose.yml`

## Docker-first quick start

From repo root:

```powershell
Copy-Item .env.example .env
# edit .env with your local values if needed
.\scripts\mcp_up.ps1
.\scripts\mcp_status.ps1
```

Toolbox endpoint:
- `http://localhost:5000/mcp` (MCP JSON-RPC endpoint)

Current MCP toolset in this project:
- `postgres_sql_query`
- `sqlite_sql_query`
- `mongodb_aggregate_business`
- `mongodb_aggregate_checkin`

DuckDB note:
- Toolbox `v0.30.0` in this setup does not expose a DuckDB source.
- Oracle Forge uses local DuckDB execution fallback (configured by `DUCKDB_PATH`) when a dataset routes to DuckDB.

Stop stack:

```powershell
.\scripts\mcp_down.ps1
```

## Manual toolbox binary (optional)

If you need non-Docker local binary execution:

```bash
export VERSION=0.30.0
curl -O https://storage.googleapis.com/genai-toolbox/v$VERSION/linux/amd64/toolbox
chmod +x toolbox
./toolbox --tools-file mcp/tools.yaml
```

Then verify:

```bash
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"tools-list","method":"tools/list","params":{}}'
```
