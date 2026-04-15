from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.evaluator import OracleForgeEvaluator


def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    parser = argparse.ArgumentParser(description="Run Oracle Forge query evaluation")
    parser.add_argument(
        "--dataset",
        default=os.getenv("DAB_DATASET", "yelp"),
        choices=["yelp"],
        help="Dataset to evaluate. Defaults to DAB_DATASET from .env.",
    )
    parser.add_argument(
        "--query",
        type=int,
        default=os.getenv("DAB_QUERY_INDEX"),
        help="Optional zero-based query index. Defaults to DAB_QUERY_INDEX from .env when set.",
    )
    args = parser.parse_args()

    if isinstance(args.query, str):
        args.query = int(args.query)

    evaluator = OracleForgeEvaluator(repo_root=ROOT)
    queries = evaluator.load_dataagentbench_queries(dataset=args.dataset)
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
