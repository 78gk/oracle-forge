# Oracle Forge Implementation Notes

## Architecture Summary

This implementation adds a full modular execution pipeline:

- `agent/main.py` exposes `run_agent(question, available_databases, schema_info)`.
- `agent/context_builder.py` loads KB architecture/domain/correction context and merges schema metadata.
- `agent/planner.py` produces a structured execution plan with multi-DB routing and dialect-aware steps.
- `agent/tools_client.py` integrates Google MCP Toolbox-compatible tool discovery/invocation from `http://localhost:5000`.
- Canonical MCP config is in `mcp/tools.yaml` and Docker stack is in `mcp/docker-compose.yml`.
- `agent/sandbox_client.py` runs planned steps inside a simulated sandbox layer and returns structured validation output.
- `agent/utils.py` provides join-key normalization, sentiment extraction, merge helpers, metrics, and confidence scoring.

All data access goes through MCP tool invocation abstractions; no direct DB drivers are used.

## MCP Connection Setup

1. Start the Dockerized MCP stack:
   - `.\scripts\mcp_up.ps1`
2. Configure DB credentials with environment variables used in `mcp/tools.yaml`:
   - `POSTGRES_DSN`
   - `MONGODB_URI`
   - `MONGODB_DATABASE`
   - `SQLITE_PATH`
   - `DUCKDB_PATH`
3. Ensure `/v1/tools` is reachable:
   - `.\scripts\mcp_status.ps1`
4. Optional:
   - `MCP_BASE_URL` to override endpoint.
   - `ORACLE_FORGE_MOCK_MODE=true` only for intentional dry-run mock execution.
   - `ORACLE_FORGE_ALLOW_MOCK_FALLBACK=false` to force fail-fast on MCP outages (default/recommended).

## DAB Adapter Integration

- Entry point for benchmark execution: `benchmark/dab_adapter.py` → `dab_entry(...)`.
- Adapter calls the same `run_agent(...)` used by local evaluation.
- Local synthetic evaluation (`eval/run_local_eval.py`) is dataset-agnostic and does not require DAB assets.
- Once DAB datasets are available, pass DAB-provided `question`, `available_databases`, and `schema_info` directly to `dab_entry(...)` with no refactor.
