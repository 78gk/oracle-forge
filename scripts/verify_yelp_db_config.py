"""Verify DataAgentBench Yelp db_config lists MongoDB, DuckDB, and PostgreSQL."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.evaluator import OracleForgeEvaluator  # noqa: E402


def main() -> None:
    ev = OracleForgeEvaluator(repo_root=ROOT)
    types = ev._extract_db_types(ROOT / "DataAgentBench" / "query_yelp")
    expected = {"mongodb", "duckdb", "postgresql"}
    missing = sorted(expected - set(types))
    print("extracted db_types:", types)
    if missing:
        print("FAIL: missing:", missing)
        sys.exit(1)
    queries = ev.load_dataagentbench_queries(dataset="yelp")
    if not queries:
        print("FAIL: no Yelp queries loaded.")
        sys.exit(1)
    first = queries[0].get("available_databases") or []
    if set(expected) - set(first):
        print("FAIL: query payload missing dbs:", first)
        sys.exit(1)
    print("OK: Yelp db_config exposes mongodb, duckdb, postgresql (evaluator + query payloads).")
    sys.exit(0)


if __name__ == "__main__":
    main()
