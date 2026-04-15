from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.dab_evaluator import run_regression_suite


def main() -> None:
    output_path = ROOT / "eval" / "regression_results.json"
    dataset_path = ROOT / "eval" / "regression_suite.json"
    report = run_regression_suite(dataset_path)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"regression_pass": report["regression_pass"], "total_queries": report["total_queries"]}, indent=2))


if __name__ == "__main__":
    main()
