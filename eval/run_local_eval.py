from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluator import LocalEvaluator


def main() -> None:
    queries_path = ROOT / "eval" / "synthetic_queries.json"
    output_path = ROOT / "eval" / "results_log.json"
    evaluator = LocalEvaluator(queries_path=queries_path)
    report = evaluator.evaluate()
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(json.dumps({"pass@1": report["pass@1"], "total_queries": report["total_queries"]}, indent=2))


if __name__ == "__main__":
    main()
