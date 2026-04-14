from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.evaluator import OracleForgeEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Oracle Forge query evaluation")
    parser.add_argument("--dataset", required=True, choices=["yelp"], help="Dataset to evaluate.")
    parser.add_argument("--query", type=int, default=None, help="Optional zero-based query index.")
    args = parser.parse_args()

    evaluator = OracleForgeEvaluator(repo_root=ROOT)
    queries = evaluator._load_dataagentbench_yelp_queries()
    if args.query is not None:
        if args.query < 0 or args.query >= len(queries):
            raise IndexError(f"Query index out of range: {args.query}. Available: 0..{len(queries)-1}")
        queries = [queries[args.query]]

    report = evaluator.evaluate_queries(queries)
    output_path = ROOT / "eval" / "results.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset": args.dataset,
                "queries_evaluated": report["total_queries"],
                "pass@1": report["pass@1"],
                "results_path": str(output_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
