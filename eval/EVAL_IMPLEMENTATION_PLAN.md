# Evaluation & correction-loop — implementation plan (testable phases)

**Status (Phases A–C implemented in-repo):** `run_agent` exposes `closed_loop`; `eval/run_dab_eval.py` supports `--scope multi`, `--per-dataset`, `--datasets`, `--trials`; `OracleForgeEvaluator.load_dataagentbench_queries_multi` + `list_dataagentbench_dataset_keys` cover all `DataAgentBench/query_*` folders. See `tests/eval/test_dataagentbench_loader.py`. Phase D (CI) and Phase E (smarter replan) remain optional follow-ups.

## 1. Assessment: is the “correction loop” implemented?

**Yes — partially, in code — but it is not visible in evaluation reports today.**

| Location | What exists |
|----------|-------------|
| `agent/planner.py` | `QueryPlanner.execute_closed_loop()` runs up to `max_replans` (default 2). On tool failure it calls `_replan_with_corrections()`, which builds a **new** plan via `create_plan()` and attaches `replan_context` (notes + `failure_types`). |
| `agent/main.py` | `run_agent()` calls `execute_closed_loop(...)` and uses the **last** attempt’s plan/results. The full `closed_loop` object (with `attempts`, per-attempt `plan`/`results`) is **not** copied into the returned `dict`. |
| `eval/run_dab_eval.py` | Writes `status`, `answer`, `query_trace`, etc. **No** `closed_loop`, `attempt_count`, or `replans` fields. |

So: the loop **runs**, but **harness output does not record it**, which is why assessments read as if there were no corrections.

### Why you often see “no replan” even when the loop exists

1. **First attempt succeeds** — no second attempt; `replans` stays 0. Common for Yelp when `postgres_sql_for_yelp_question()` injects curated SQL that executes cleanly.
2. **Replan is shallow** — `_replan_with_corrections` calls `create_plan()` again with the **same** question; for Yelp, the same template SQL is often produced, so the second attempt may fail the same way (loop exits without a visible “fix”).
3. **Trace noise** — MCP/tool lines are in `query_trace`; there is no single structured “closed_loop” event unless we add it (planned in Phase A).

---

## 2. Datasets under `DataAgentBench` (`query_*` folders)

There are **12** dataset directories in this repo (alphabetical):

- `query_agnews`
- `query_bookreview`
- `query_crmarenapro`
- `query_DEPS_DEV_V1`
- `query_GITHUB_REPOS`
- `query_googlelocal`
- `query_music_brainz_20k`
- `query_PANCANCER_ATLAS`
- `query_PATENTS`
- `query_stockindex`
- `query_stockmarket`
- `query_yelp`

`eval/evaluator.py` already loads one folder via `load_dataagentbench_queries(dataset)` where `dataset` maps to `DataAgentBench/query_{dataset}` (or `query_*` if the key already includes `query_`).

**Note:** `eval/dab_pg_mongo_queries.json` is a **separate** harness file, not under `DataAgentBench/query_*`. Include it only if you explicitly extend the plan beyond DAB folders.

---

## 3. Desired evaluation modes (requirements)

| Mode | Behavior |
|------|----------|
| **Per-dataset cap `N`** | For **each** of the 12 `query_*` datasets, take the **first `N` queries** (sorted by existing `_query_sort_key`: `query1`, `query2`, …). |
| **`all`** | For **each** dataset, load **all** `query*/query.json` entries; concatenate into one run (optionally tag each row with `dataset` for reporting). |
| **CLI** | e.g. `--dab-scope multi`, `--per-dataset 2` **or** `--per-dataset all`; retain backward compatibility with single `--dataset yelp`. |

Environment-variable-only control is possible (`DAB_DATASETS`, `DAB_QUERIES_PER_DATASET`) but **argparse** is clearer for “all vs N” and for CI.

---

## 4. Phased implementation plan (each phase is testable)

### Phase A — Make the correction loop **observable** (no behavior change to planning)

**Goal:** Any assessment JSON / API consumer can see whether replanning occurred.

**Work**

1. Add `_closed_loop_summary(closed_loop_result) -> dict` in `agent/main.py` (or small helper module).
2. Attach to every `run_agent` response:
   - `closed_loop`: `{ ok, attempt_count, replans, attempts: [{ attempt, all_steps_ok, replan_context }] }`
3. Append one **`query_trace` event** with `event: "closed_loop"` (compact summary) so logs stay grep-friendly.
4. Extend `eval/run_dab_eval.py` (and `eval/evaluator.py` sentinel rows if used) to persist `closed_loop` per trial.

**Tests**

- Unit test: mock `execute_closed_loop` to return 2 attempts with first failing → `replans == 1` and `replan_context` present in summary.
- Manual: run one failing query → `eval/results.json` shows `closed_loop` on each trial.

**Exit criteria:** `eval/results.json` contains structured correction-loop fields; README snippet documents the fields.

---

### Phase B — Multi-dataset discovery + slicing in `OracleForgeEvaluator`

**Goal:** One API to build the query list for “12 datasets × first N queries” or “12 datasets × all queries”.

**Work**

1. `list_dataagentbench_dataset_dirs() -> List[str]` — scan `DataAgentBench/query_*` directories (exclude non-dataset noise if any).
2. `load_dataagentbench_queries_multi(*, per_dataset: Optional[int])`:
   - `per_dataset is None` → all queries from each dataset (mode **all**).
   - `per_dataset == N` → `load_dataagentbench_queries(ds)[:N]` per dataset (use existing sort order).
3. Each query dict gets `"dataset": "<short_name>"` where short name is e.g. `yelp` for `query_yelp`, `DEPS_DEV_V1` for `query_DEPS_DEV_V1` (strip `query_` prefix consistently).

**Tests**

- With fixture or real repo: `per_dataset=2` → exactly `12 * 2 = 24` queries if every dataset has ≥2 queries (skip or warn if a dataset has fewer — define policy: **min available** vs **fail fast**).
- Assert every row has `dataset` and `validator_path` where present.

**Exit criteria:** Pure-Python tests pass; no `run_agent` calls required.

---

### Phase C — CLI for `run_dab_eval.py` (replace env-only toggles)

**Goal:** Explicit arguments:

- `--dab-scope {single,multi}` — default `single` for backward compatibility.
- `--dataset NAME` — used when `dab-scope=single` (current behavior).
- `--per-dataset {all,N}` — when `dab-scope=multi`: `all` = full exhaust per dataset; integer `N` = first N per dataset.
- Optional: `--datasets` comma list to **subset** the 12 (e.g. smoke: `yelp,agnews`).

**Work**

1. Use `argparse`; map to `OracleForgeEvaluator.load_*` from Phase B.
2. Embed metadata in results JSON: `dab_scope`, `per_dataset`, `datasets_included`, `total_queries`.

**Tests**

- `python eval/run_dab_eval.py --help` shows new flags.
- Dry run with `--dab-scope multi --per-dataset 2` prints `total_queries` == 24 if all datasets have ≥2 queries.

**Exit criteria:** Documented in README “Evaluation” section; old env vars still work or are deprecated in one release note line.

---

### Phase D — Cross-dataset smoke in CI (optional, fast)

**Goal:** Nightly or PR job runs `multi` + `--per-dataset 2` + `DAB_TRIALS_PER_QUERY=1` to sanity-check wiring without 50×full-matrix cost.

**Exit criteria:** CI job green; artifact uploads `results.json` with `closed_loop` stats.

---

### Phase E — (Separate track) **Smarter replanning**

**Goal:** Corrections that change outcomes, not only annotations.

**Work (larger change)**

- Feed `failure_types` into SQL/pipeline synthesis (or LLM repair step) instead of only `replan_context` text.
- Yelp template path: avoid identical SQL on replan when prior attempt failed.

**Tests:** Regression cases where attempt 1 fails and attempt 2 uses a different `predicted_queries` entry.

**Exit criteria:** Measurable increase in “recovered after replan” rate on a fixed failure set.

---

## 5. Suggested order of execution

1. **Phase A** (visibility) — unblocks honest assessment of the existing loop.  
2. **Phase B** (data loading) — unblocks multi-dataset evaluation.  
3. **Phase C** (CLI) — makes modes usable day-to-day.  
4. **Phase D** (CI smoke) — optional guardrail.  
5. **Phase E** — only after A–C prove the harness; otherwise you optimize an invisible metric.

---

## 6. Quick reference: files to touch (when implementing)

| Phase | Primary files |
|-------|----------------|
| A | `agent/main.py`, optionally `agent/user_facing_format.py`, `eval/run_dab_eval.py`, `eval/evaluator.py` |
| B | `eval/evaluator.py` |
| C | `eval/run_dab_eval.py`, `README.md` |
| D | `.github/workflows/*` or local script |
| E | `agent/planner.py`, possibly `agent/llm_reasoner.py` |

This plan stays aligned with `kb/architecture/openai_layers.md` (Layer C corrections) and `kb/evaluation/dab_scoring_method.md` once you decide whether pass@1 uses **first attempt** vs **final** answer after replan — document that choice when Phase A lands.
