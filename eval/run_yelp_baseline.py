from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.evaluator import OracleForgeEvaluator


def main() -> None:
    evaluator = OracleForgeEvaluator(repo_root=ROOT)
    report = evaluator.evaluate_yelp_dataset()
    results_path = ROOT / "eval" / "results.json"
    score_log_path = ROOT / "eval" / "score_log.jsonl"
    results_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log_entry = {
        "stage": "baseline",
        "dataset": "yelp",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_queries": report["total_queries"],
        "pass@1": report["pass@1"],
        "confidence_interval_95": report["confidence_interval_95"],
    }
    with score_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "dataset": "yelp",
                "total_queries": report["total_queries"],
                "pass@1": report["pass@1"],
                "results_path": str(results_path),
                "score_log_path": str(score_log_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
