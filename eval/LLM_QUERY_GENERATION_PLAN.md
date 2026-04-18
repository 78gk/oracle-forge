# LLM-driven query generation (replace Yelp SQL oracle) — detailed plan

**Implementation status (2026):** Core pieces are in the repo: `agent/query_safety.py` (pre-execution validation), `agent/llm_query_generator.py` (Groq/OpenRouter JSON steps), `agent/planner.py` (gated by `ORACLE_FORGE_LLM_SQL`, replan passes errors into the generator), `agent/main.py` (validates each step before MCP). Default remains `ORACLE_FORGE_LLM_SQL=false` for backward compatibility with Yelp templates.

This document aligns with **`kb/`** (architecture, domain, corrections) and describes how to remove `agent/dab_yelp_postgres.py` **exact-string → SQL** mapping, add **LLM-produced** SQL/Mongo pipelines using existing **KB + schema context**, add **unsafe-query validation**, and wire **self-correction** for failed generation or execution.

---

## 1. What the KB says we should build

| KB reference | Requirement for this work |
|--------------|---------------------------|
| `kb/architecture/openai_layers.md` | **Layer A (Schema)** + **Layer B (institutional: joins, terms)** + **Layer C (corrections)** feed reasoning. **Layer 6**: closed-loop — execute → validate → on failure → retrieve correction → retry. |
| `kb/architecture/conductor_worker_pattern.md` | Conductor parses NL → picks DBs, join keys, extraction → **workers** get **DB-scoped** knowledge → merge. Failure → log + **replanned** worker with correction context. |
| `kb/architecture/tool_scoping_philosophy.md` | **Narrow tools** per engine (`query_postgres(sql)`, `query_mongodb(pipeline)`, …). SQL vs aggregation pipeline are different surfaces — generation must be **dialect-aware**. |
| `kb/domain/joins/*`, `kb/domain/databases/*` | Join key formats, schema conventions — must appear in the **prompt context** for the LLM (already partially loaded via `ContextBuilder`). |
| `kb/corrections/*` | `failure_log` / `resolved_patterns` inform **replan** messaging; regression suite protects known-good behavior. |

**Gap today:** Routing uses the LLM (`GroqLlamaReasoner.plan`) but only returns `selected_databases` + loose `query_hints`. **Concrete SQL** for Postgres often comes from **`postgres_sql_for_yelp_question()`** (exact question match) or **heuristic templates** in `QueryPlanner._build_query_payload` — not LLM-generated, and not aligned with “success metric: resolve join mismatch via KB.”

---

## 2. Current behavior (baseline to replace)

- **`agent/dab_yelp_postgres.py`**: `POSTGRES_SQL_BY_QUESTION` — if `question.strip()` equals a key, inject hand-written SQL.
- **`agent/planner.py`**: `_build_query_payload` uses that SQL for Postgres; Mongo uses tiny keyword pipelines; else generic `SELECT *` / `COUNT` / `health_check`.
- **`agent/llm_reasoner.py`**: Single call, JSON with `selected_databases`, `rationale`, `query_hints` — **no** validated SQL/Mongo body in the contract.
- **`execute_closed_loop`**: Retries on **tool execution** failure; replan does **not** currently vary generation based on “unsafe SQL” or “wrong semantics” before execution.

---

## 3. Target architecture

### 3.1 Two-stage LLM contract (recommended)

Keep **Stage 1 — routing** (cheap, small JSON): which DBs, high-level intent, join keys hints (existing `plan()` pattern).

Add **Stage 2 — generation** (per selected DB, or one structured response):

- **Input:** Natural question, `routing_question`, `available_databases`, **trimmed** `context_layers` (KB), **`schema_metadata`** for allowed engines only, `llm_guidance.query_hints`, and **correction text** on replan.
- **Output (strict JSON):**  
  - `steps: [{ "database": "postgresql", "dialect": "sql", "sql": "..." } | { "database": "mongodb", "dialect": "mongodb_aggregation", "collection": "...", "pipeline": [...] } | ...]`  
  - Optional: `answer_shape` / `post_processing` hints for `_answer_from_metrics` replacement later.

**Why two stages:** Routing + full SQL in one call often hits token limits and mixes concerns; KB already loads large context — Stage 2 can be **scoped per engine** (Postgres worker vs Mongo worker), matching `conductor_worker_pattern.md`.

### 3.2 Where generation runs

**Option A (minimal change):** Extend `QueryPlanner.create_plan` / new `QueryGenerator` class: after `_select_databases`, call **`generate_queries_llm(...)`** instead of `_build_query_payload` heuristics + Yelp map.

**Option B (closer to KB):** Introduce explicit **worker** functions that receive **only** `postgresql_schemas` + join snippets for Postgres, analogous for Mongo — then **orchestrator** merges. Heavier refactor; clearer separation.

**Recommendation:** Start with **Option A** behind `ORACLE_FORGE_LLM_SQL=1`, keep planner structure; refactor toward **Option B** if multi-DB generation quality plateaus.

### 3.3 Remove Yelp oracle path

- **Delete or gate** `postgres_sql_for_yelp_question` usage in `_build_query_payload` when LLM generation is enabled.
- **Keep** `POSTGRES_SQL_BY_QUESTION` only for **offline regression** / parity tests (`eval/` or `scripts/verify_yelp_templates.py`) if you still need to diff behavior — not in the default `run_agent` path.

---

## 4. Unsafe-query validation (before MCP execute)

Implement **`QuerySafetyValidator`** (new module, e.g. `agent/query_safety.py`):

### 4.1 SQL (Postgres, SQLite, DuckDB)

- **Parse** with a lightweight SQL parser (e.g. `sqlparse` — add dependency — or dialect-specific allowlist) to:
  - Reject **multiple statements** (`;` separated).
  - Reject **DDL/DML**: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, …
  - Reject dangerous **pragmas** / extensions if applicable.
- **Allowlist identifiers** to **schema_metadata**-known **tables** (and optionally **columns**) for the target engine. Reject unknown tables/columns (configurable strictness: **strict** for eval, **warn** for dev).
- **Length cap** on query string.
- **Mongo:** Validate `pipeline` is a **list** of dicts; reject `$where` with arbitrary JS if you treat that as unsafe; cap stages; allowlist **collection** names from schema metadata.

### 4.2 Output shape

- `validate_sql(engine, sql, schema_subset) -> Ok | Err(reason_code, message)`
- On failure: **do not execute**; return structured error to the **self-correction** loop.

This matches `regression_prevention.md` spirit (**Q089: SQL to MongoDB → input validation**): validate **before** the wrong engine sees the payload.

---

## 5. Self-correction loop (generation + execution)

Align with **Layer 6** and existing `execute_closed_loop`:

### 5.1 Failure classes

| Failure | Action |
|---------|--------|
| **Safety validation failed** | Append `failure_types: ["unsafe_sql" \| "schema_violation" \| ...]`; replan prompt includes **validator message** + last bad SQL/pipeline (redacted if huge). |
| **LLM JSON parse / schema invalid** | Retry generation once with stricter system message; then fallback or fail. |
| **MCP execution error** (existing) | Map `error_type` to replan (already partially in `_replan_with_corrections`). |
| **Answer validation failed** (optional later) | DAB `validate.py` false negative — separate track; do not conflate with tool error. |

### 5.2 Replan prompt content

- Previous **attempt** SQL/pipeline (or summary).
- **Validator** or **database** error text (sanitized).
- Snippets from **`kb/corrections/failure_log.md`** / **`resolved_patterns.md`** when `failure_signature` matches (future: `search_correction_log`-style retrieval).

### 5.3 Limits

- Keep `max_replans` bounded; separate **generation retries** from **tool retries** (`MCPToolsClient.execute_with_retry`) for clarity in traces.

---

## 6. Implementation phases (testable)

### Phase 0 — Baseline & feature flags

- Document current pass@1 / trial results with Yelp oracle **on** (snapshot).
- Add env: `ORACLE_FORGE_LLM_SQL` (default `false` initially), `ORACLE_FORGE_SQL_STRICT_ALLOWLIST` (default `true` in eval).

**Test:** CI or local script asserts flag toggles code path without running DB.

---

### Phase 1 — Safety validator only

- Implement `query_safety.py` + unit tests: forbidden keywords, multi-statement, allowlist tables from a **fixture** schema.

**Test:** Golden tests for allowed/blocked SQL strings; no LLM yet.

---

### Phase 2 — LLM generation module (no Yelp oracle when flag on)

- New: `agent/llm_query_generator.py` (or extend `llm_reasoner.py`):
  - `generate_plan_steps(question, context, selected_databases, schema_metadata) -> List[PlanStepDict]`
  - Prompt: KB layers + **JSON schema** for output; temperature 0; higher `max_tokens` than routing-only call.
- `QueryPlanner`: if `ORACLE_FORGE_LLM_SQL=1`, skip `postgres_sql_for_yelp_question` and skip heuristic SQL; use generated steps; still run **safety validator** before execute.

**Test:** Mock LLM returns fixed JSON → planner produces expected payloads → validator accepts/rejects.

---

### Phase 3 — Wire self-correction for validation + execution

- On validator failure or tool failure, call **regenerate** with error context (bounded turns).
- Extend `closed_loop` / trace with `generation_attempt`, `validation_errors`, `replan_context`.

**Test:** Integration test with mock MCP failing once then succeeding (or mock validator fail then pass after replan).

---

### Phase 4 — Remove default Yelp oracle

- Default `ORACLE_FORGE_LLM_SQL=true` or remove dead code path after metrics OK.
- Move `POSTGRES_SQL_BY_QUESTION` to **tests/fixtures** or `scripts/` for regression only.

**Test:** `verify_yelp_templates.py` becomes “parity optional” or compares **LLM output** statistics, not exact SQL match.

---

### Phase 5 — KB alignment hardening

- **Trim** prompts per worker: inject `domain/databases/postgresql_schemas.md` + relevant join doc only when Postgres selected (per `memory.md` on-demand loading — optional optimization).
- Replace `_answer_from_metrics` keyword hacks with **schema-aware** or **LLM summarization** step (separate small task).

---

## 7. Recommendations

1. **Do not** remove Yelp templates from the repo until Phase 4 metrics are acceptable — use **feature flag** for rollback.
2. **Token budget:** Generation prompts are larger than routing-only; increase `MAX_PROMPT_TOKENS` or split per-DB calls; monitor cost/latency.
3. **Strict allowlist** in eval, looser in local dev to avoid blocking exploration.
4. **sqlparse** (or similar) is worth a dependency for robust blocking of multi-statement and DDL; regex-only is error-prone.
5. **Mongo pipelines:** LLM should output **JSON array** only; validate with `jsonschema` or manual stage walk.
6. **Observability:** Log `predicted_queries` + `validation_result` + `replan` to `docs/driver_notes/` or structured JSONL for debugging (already partially there).
7. **Evaluation:** Re-run `eval/run_dab_eval.py` with `--scope multi --per-dataset 2` before/after to measure **real** generalization drop when oracle is off — expect initial drop until prompts and replan improve.

---

## 8. Files likely touched (summary)

| Area | Files |
|------|--------|
| Remove / gate oracle | `agent/dab_yelp_postgres.py`, `agent/planner.py`, `scripts/verify_yelp_templates.py` |
| LLM generation | `agent/llm_reasoner.py` or new `agent/llm_query_generator.py`, `agent/main.py` (orchestration) |
| Safety | New `agent/query_safety.py`, `requirements.txt` / `pyproject.toml` if adding `sqlparse` |
| Replan | `agent/planner.py` (`_replan_with_corrections`, `execute_closed_loop`) |
| KB | No rewrites required initially — ensure `ContextBuilder` continues to pass `schema_metadata` + layers into generator prompts |
| Docs | `README.md`, this file, optional `kb/evaluation/` note on pass@1 vs generation |

---

## 9. Success criteria

- No production path uses **exact question string → SQL** map for Yelp.
- Every executed SQL/pipeline passes **safety validation** or is rejected with a logged reason.
- Failed validation or execution triggers **at least one** documented replan attempt with error context in traces.
- DAB eval can run with **LLM generation** enabled and produce measurable pass@1 with documented confidence intervals.
