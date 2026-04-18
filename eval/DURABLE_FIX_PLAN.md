# Durable fix plan — all queries, all databases

**Purpose:** A stable roadmap so the agent behaves correctly for (a) the **DataAgentBench-style harness** (including the ~54 queries across `query_*` datasets), and (b) **arbitrary user questions** against **any** configured engine (PostgreSQL, MongoDB, SQLite, DuckDB), without one-off dataset hacks.

**Related docs (do not duplicate; extend):**

- `eval/EVAL_IMPLEMENTATION_PLAN.md` — multi-dataset eval, closed-loop visibility (largely done).
- `eval/LLM_QUERY_GENERATION_PLAN.md` — LLM SQL/Mongo generation, safety validator, replan wiring (core implemented; quality gaps remain).

**Problems this plan addresses (observed):**

| Symptom | Root cause class |
|--------|-------------------|
| `execution_match=False` with empty `records` | Answer merge drops non-joined step outputs; success path still yields no comparable values. |
| `column "stars" does not exist` on `business` | Generation assumes a schema shape that does not match **live** introspection + benchmark seed. |
| Agnews tasks query Yelp `review` / `business` | **Routing + connection** point Mongo/SQLite at **one** static DB per engine, not **dataset-scoped** stores. |
| Replan repeats same SQL | Replan injects **generic** notes, not **structured** `{engine, missing_column, candidates}` from execution errors. |
| KB “does nothing” | KB is **bulk JSON** with hard caps; **structured** schema + join rules are not first-class in generation prompts. |

---

## 1. North-star invariants

These invariants should hold for **every** query:

1. **Single source of truth for “what exists”:** Any table/collection/column used in a generated query must appear in **authoritative schema** for that **engine + logical dataset** (see §2). No silent reliance on prose in `kb/domain/databases/*.md` when it conflicts with introspection.

2. **Fail closed before execution:** Invalid identifiers or unsafe operations are caught **before** MCP (existing `validate_step_payload` — extend with richer semantics, not weaker rules).

3. **Answer contract for evaluation:** Final `answer` must be **deterministic** for the harness: either a **scalar/list** comparable to `ground_truth.csv`, or a **normalized row set** the evaluator can stringify consistently (see `eval/evaluator.py`).

4. **Observable pipeline:** Every run exposes **which dataset**, **which DSN/DB name**, **schema snapshot id**, and **merge strategy** used — enough to reproduce failures without guessing.

---

## 2. Schema and dataset isolation (foundation)

**Goal:** Eliminate “Yelp-shaped Mongo while running agnews” class bugs.

### 2.1 Logical dataset identity

- Introduce a **`dataset_id`** (or `logical_scope`) carried from harness → `run_agent` → planner → tools (optional string, default `None` for ad-hoc users).
- **DataAgentBench:** Set `dataset_id` from folder name (`agnews`, `yelp`, …) in `eval/run_dab_eval.py` / loader.
- **User/API:** Allow optional `dataset_id` or explicit **`connection_profile`** in the request payload.

### 2.2 Connection profiles (durable multi-benchmark)

- Move from **one global** `MONGODB_DATABASE`, `SQLITE_PATH`, `DUCKDB_PATH` in `.env` to a **map**:

  - e.g. `config/datasets.yaml` or env `ORACLE_FORGE_DATASET_<ID>_MONGODB_URI` / `_SQLITE_PATH` / …
  - MCP toolbox (`mcp/tools.yaml`) or tool factory selects **profile** by `dataset_id`.

- **Fallback:** When `dataset_id` is absent, use **default** profile (current behavior) for backward compatibility.

### 2.3 Schema bundle per execution

- For each plan step, attach **`schema_ref`**: `{ engine, dataset_id?, tables[], collections[], columns_by_table }` from **live introspection** merged with **query JSON `schema_info`** (benchmark ground truth).
- **Rule:** LLM generation prompts list **only** this bundle (plus join hints), not unbounded KB markdown, for **identifier grounding**.

**Exit criteria:** Running `agnews` and `yelp` back-to-back uses **different** SQLite/Mongo targets when configured; introspection reflects the **opened** DBs.

---

## 3. Routing and database selection

**Goal:** Correct engines for the question **and** for the **dataset** (not only keyword heuristics).

### 3.1 Router inputs

- Pass **`dataset_id`**, **`schema_ref` summary** (table/collection names only), and **first line of benchmark instructions** into `GroqLlamaReasoner.plan()` (or a thin wrapper).
- Constrain **`selected_databases`** to those present in **both** `available_databases` **and** non-empty schema for this profile.

### 3.2 Multi-DB policy

- Define explicit **when to multi-plan**: e.g. join/cross-doc questions vs single-engine lookups — avoid defaulting to `[postgresql, mongodb]` for every question unless schema supports both.

**Exit criteria:** Misroutes (e.g. stock index questions hitting `review`) drop measurably on DAB; router logs show **rationale + schema evidence**.

---

## 4. Query generation (LLM + workers)

**Goal:** Align with `LLM_QUERY_GENERATION_PLAN.md` Stage 2, but make it **dataset-safe**.

### 4.1 Prompt structure (replace raw KB dump for identifiers)

- **Keep** architecture/corrections as **short** summaries or retrieved chunks (optional RAG later).
- **Require** the **schema bundle** + **dialect rules** as the **primary** generation context.
- Inject **extracted** join-key rows (from `join_key_mappings.md` or structured YAML) as **tables**, not only regex sidecars in `ContextBuilder`.

### 4.2 Optional per-engine workers (recommended medium term)

- **Postgres worker:** receives only `postgresql` schema + question slice.
- **Mongo worker:** receives only allowed **collections** + field paths from introspection.
- Orchestrator merges steps; reduces cross-dialect hallucination.

### 4.3 Replan that changes behavior

- Parse execution errors into **structured** facts: `missing_column`, `unknown_table`, `syntax`, `wrong_collection`.
- Append **concrete** constraints on the next generation call: “do not use `stars` on `business`; candidates: `review.stars`” when introspection shows it.

**Exit criteria:** Same question after a **schema error** produces **different** SQL/pipeline, not a repeat of the failed query (track in `runtime_corrections.jsonl`).

---

## 5. Execution, safety, and tools

- **Expand** `query_safety` to understand **qualified** names and **Mongo** stages (deny writes; allow read stages only).
- **Tool surfaces:** Prefer **generic** `query_postgres` / `query_mongodb` with **dynamic** connection from profile over hardcoded `mongodb_aggregate_business` where possible (or map tool name → profile internally).

---

## 6. Answer synthesis and merge (critical for eval parity)

**Goal:** Fix empty `records` when tools return data.

### 6.1 `_merge_outputs` behavior

- If **join keys** cannot be inferred or **left side is empty**, **fallback strategies** (in order):
  1. Prefer the **single non-empty** step result for **single-intent** questions (detect via planner flag or question classifier).
  2. **Concatenate** disjoint row sets with a **`source_step`** column for traceability.
  3. Only then return empty merge **with explicit** `merge_failure_reason` in trace.

### 6.2 `_answer_from_metrics` / evaluator alignment

- Add **question-type** or **expected_shape** from planner (e.g. `single_value`, `ordered_list`, `table`) so final answer is not always `{metrics, records}`.
- Map common DAB shapes (title string, numeric average, list of categories) to **scalar or list** outputs the evaluator already normalizes.

**Exit criteria:** Agnews-style “title” queries with one successful SQL step yield a **non-empty** normalized answer; Yelp averages return **numeric** comparison where ground truth is numeric.

---

## 7. Evaluation harness and the “54 queries”

- **Single command** to run **all** DAB queries: `--scope multi --per-dataset all` (already supported).
- **Per-dataset reporting:** Pass rate by `dataset_id`; fail **taxonomy** (`schema_error`, `routing`, `merge_empty`, `execution_match`).
- **Golden tests:** Small pytest suite with **mocked MCP** returning fixed schema + rows to lock merge + answer shape **without** Docker.
- **Regression gate:** Optional CI job: `per-dataset 1` across all 12 folders + merge unit tests on PR.

---

## 8. Phased rollout (recommended order)

| Phase | Focus | Delivers |
|-------|--------|----------|
| **A** | Merge + answer fallback | Non-empty answers when any step succeeds; fewer false `execution_match=False`. |
| **B** | Schema bundle + generation prompt | Fewer hallucinated columns/tables; better replan. |
| **C** | Dataset connection profiles | Correct DB per benchmark; fixes cross-dataset contamination. |
| **D** | Router + multi-DB policy | Right engine selection for open-domain users. |
| **E** | Per-engine workers (optional) | Higher quality on complex multi-DB questions. |
| **F** | Hardening + CI | Sustained quality on 54+ queries and arbitrary users. |

Each phase should ship with **tests** and a short **README** section; no phase depends on “prompt vibes” alone.

---

## 9. Risks and non-goals

- **Non-goal:** Perfect accuracy on adversarial NL without schema — always require **some** schema surface (introspection or supplied `schema_info`).
- **Risk:** Over-constraining LLM with allowlists may block valid queries if introspection is incomplete — mitigate with **explicit** `schema_info` from benchmarks and **human-in-the-loop** connection profiles for exotic user DBs.
- **Risk:** Larger prompts — mitigate with **per-engine** calls and **summarized** KB, not one 12k JSON blob.

---

## 10. Success metrics

| Metric | Target |
|--------|--------|
| DAB multi (`per-dataset all`) pass@1 | Trend upward phase-over-phase; track per `dataset_id`. |
| Empty `answer.records` when ≥1 tool returned rows | **0** after Phase A. |
| Repeated identical failed SQL across replans | **Rare** after Phase B–C. |
| User ad-hoc query (single DB, schema known) | Executes read-only query or returns **actionable** error, never silent wrong DB. |

---

**Document owner:** Update this file when phases complete or priorities shift; link concrete PRs/issues in a short changelog section below when you start using it.

### Changelog

- **2026-04-17:** Initial plan (merge, schema truth, dataset profiles, routing, eval gates).
- **2026-04-17:** **Phases A–C implemented:** (A) `_merge_outputs` fallbacks (`single_non_empty_step`, `concat_disjoint`) + `merge_info` on success; `_answer_from_metrics` returns string for `title` column when present. (B) `schema_bundle` / `schema_bundle_json` in `ContextBuilder`; routing + `LLMQueryGenerator` prioritize bundle over raw KB JSON; `enrich_replan_notes()` adds schema_constraint lines from execution errors. (C) `dataset_id` on `run_agent` / eval harness; `eval/datasets.json` + env `ORACLE_FORGE_DATASET_<KEY>_*` via `push_profile_env` for MCP-facing connection vars; `MCPToolsClient(duckdb_path=...)`. Tests: `tests/agent/test_durable_fix_phases.py`.
- **2026-04-17:** **Phase D implemented:** `utils/routing_policy.py` — `engines_with_nonempty_schema`, `build_schema_routing_summary`, `multi_db_warranted`, `collapse_multi_db_selection`, `normalize_routing_selection` (schema overlap scoring + stock/analytics keywords for DuckDB). `GroqLlamaReasoner.plan()` receives `user_question`, `routing_question` via context; prompt adds dataset id, task first line, schema summary; system message instructs minimum DB set; post-process applies `normalize_routing_selection`. `QueryPlanner._select_databases` normalizes LLM, `QueryRouter`, and rulebook paths. `run_agent` sets `context["user_question"]` and `context["routing_question"]`. Tests: `tests/agent/test_routing_policy.py`.
- **2026-04-17:** **Phase F (finalize):** `run_agent_contract` returns `dataset_id`, `merge_info`, `plan`, `validation_status`, `metrics`, `predicted_queries` for API parity with `run_agent`. `eval/run_dab_eval.py` writes **`per_dataset_summary`** (per-folder pass@1) into `results.json`, score log, and CLI JSON. **`tests/integration/test_run_agent_smoke.py`** — mock MCP (`ORACLE_FORGE_MOCK_MODE=true`) smoke tests without Docker. README documents Durable Fix Plan + `pytest tests/`. CI (`.github/workflows/ci-cd.yml`) already runs full `pytest tests/` on PR/push.
