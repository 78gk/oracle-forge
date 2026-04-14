# Oracle Forge Refinement Notes (2026-04-14)

## Scope
- Refined agent context layering, closed-loop execution, schema introspection integration, join normalization integration, and evaluation trace format.
- Kept modular architecture intact (agent/context/planner/tools/sandbox/eval modules preserved).
- Did not modify `kb/`, probes source materials, or reference documents.

## Implemented Refinements
- Added structured three-layer context contract in `agent/context_builder.py`:
  - `v1_architecture`
  - `v2_domain`
  - `v3_corrections`
- Added schema introspection utility integration:
  - New `utils/schema_introspection_tool.py`
  - Used by `agent/main.py` as the schema metadata source.
- Reworked planner into bounded closed-loop flow in `agent/planner.py`:
  - plan → execute → diagnose failure types → replan using corrections context → bounded retries.
- Replaced join merge normalization with `utils.join_key_resolver.JoinKeyResolver` integration in `agent/utils.py`.
- Added architecture disclosure to every agent response in `agent/main.py`:
  - MCP tools used
  - KB layers accessed
  - confidence score
- Added safe failure behavior and sanitized error summaries (no raw error exposure).
- Added runtime logging:
  - `docs/driver_notes/runtime_corrections.jsonl`
  - `docs/driver_notes/agent_runtime_log.jsonl`

## Evaluation Refinements
- Upgraded `eval/evaluator.py` to Sentinel-style per-query trace schema:
  - input query
  - generated query
  - tool calls
  - execution time
  - result
  - correctness
- Added local query runner:
  - `eval/run_query.py`
  - Supports `eval/run_query.py --dataset yelp --query <index>`
  - Writes `eval/results.json`.
- Added DataAgentBench Yelp validator integration via `query*/validate.py`.
- Added failure-category classification in evaluator output:
  - multi-database routing errors
  - join/key mismatch errors
  - domain knowledge gaps

## Determinism Notes
- Deterministic fallback preserved through existing mock/tool behavior.
- DataAgentBench query/ground-truth mapping is file-driven (not inline hardcoded constants).
