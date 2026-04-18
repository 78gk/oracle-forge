# Phase 5 — Fork-style harness + benchmark artifacts

## CLI

- **`python -m eval.run_dab_eval`** — full argparse (includes **`--query-ids`** / **`--query_ids`**).
- **`python -m eval.harness`** — README-style aliases:
  - `--datasets yelp` → `--scope single --dataset yelp`
  - `--datasets yelp agnews` → `--scope multi --datasets yelp,agnews`
  - `--query_ids 1` → `--query-ids 1`
  - `--n_trials N` → `--trials N`

## Outputs

Each run writes:

- `eval/results.json` — primary report  
- `eval/benchmark_<UTC_timestamp>.json` — copy for history  
- `eval/latest.json` — copy of the same run (fork-style “latest”)  
- Appends one line to `eval/score_log.jsonl`

## Queries

If **no queries** load (missing `DataAgentBench`, bad `--dataset`, or `--query-ids` filter matches nothing), the process **exits with code 2** and prints a JSON hint.

## Dataset id on every query

`eval/evaluator.py` now sets **`dataset`** on each loaded query so `run_agent(..., dataset_id=...)` receives the short key (e.g. `yelp`).

## E2E script

`scripts/e2e_real_data_smoke.ps1` — checks **`GET /health`**, **`GET /v1/tools`**, then runs **`python -m eval.harness --datasets yelp --query_ids 1 --n_trials 1`** if `DataAgentBench/` exists.
