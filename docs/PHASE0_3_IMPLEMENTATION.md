# Phases 0–3 implementation (rafia MCP + Docker)

## Phase 0 — Safety

- Git tag (if the repo is a git checkout): `pre-rafia-mcp-phases-0-3`
- **Log and trace files were not deleted or truncated.** Existing JSONL under `docs/driver_notes/` and `logs/` is unchanged.
- Reference clone for manual diff (optional, outside this repo): `D:\FDE-Training\data-agent-forge-ref` from [rafia-10/data-agent-forge](https://github.com/rafia-10/data-agent-forge).

## Phase 1 — Dependencies

- Added `agent/requirements.txt` (aligned with the reference repo).
- Root `requirements.txt` includes `-r agent/requirements.txt` so `pip install -r requirements.txt` pulls FastAPI, uvicorn, psycopg2-binary, etc.

## Phase 2 — Unified MCP code

Copied and committed Python modules under `mcp/`:

- `mcp_server.py`, `db_config.py`, `postgres_tools.py`, `mongo_tools.py`, `sqlite_tools.py`, `duckdb_tools.py`, `__init__.py`

Local adjustments:

- `db_config.py`: default `DAB_PATH` resolves to `<repo_root>/DataAgentBench` when unset; `PG_PASSWORD` default `postgres` (matches our Docker Postgres).
- `mcp_server.py`: `MCP_HOST` env (default `127.0.0.1`, use `0.0.0.0` in Docker).
- Renamed `mcp/tools.yaml` → `mcp/tools.microsoft-toolbox.legacy.yaml` (Toolbox only).

## Phase 3 — Docker Compose

- **Default** MCP service: **`mcp-server`** (Python 3.12 slim, installs FastAPI stack on start, runs `python -m mcp.mcp_server`).
- **Legacy Toolbox**: service **`toolbox`** moved to profile **`legacy-toolbox`**, host port **5001**, uses the renamed YAML file.
- **Streamlit** (`profile: ui`): now depends on **`mcp-server`** and sets `MCP_BASE_URL=http://mcp-server:5000`.
- Scripts **`scripts/mcp_up.ps1`** and **`scripts/mcp_status.ps1`** updated for `GET /health` and `GET /v1/tools`.

## Phase 4 — Agent client (done)

See **`docs/PHASE4_UNIFIED_MCP_AGENT.md`**. `MCPToolsClient` prefers **unified REST** (`GET /v1/tools`, `POST /v1/tools/{name}`) and falls back to Toolbox **`/mcp`** when needed.

## Quick verify

```powershell
cd mcp
docker compose up -d postgres mongo mcp-server
curl http://localhost:5000/health
curl http://localhost:5000/v1/tools
```
