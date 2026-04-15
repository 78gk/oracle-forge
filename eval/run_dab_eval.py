from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.main import run_agent
from eval.evaluator import OracleForgeEvaluator


def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    eval_root = ROOT / "eval"
    eval_root.mkdir(parents=True, exist_ok=True)
    trials = int(os.getenv("DAB_TRIALS_PER_QUERY", "50"))
    dataset = os.getenv("DAB_DATASET", "yelp")

    evaluator = OracleForgeEvaluator(repo_root=ROOT)
    queries = evaluator.load_dataagentbench_queries(dataset=dataset)

    all_query_reports: List[Dict[str, Any]] = []
    total_first_correct = 0
    total_trial_correct = 0
    total_trials = 0

    for query in queries:
        trials_report: List[Dict[str, Any]] = []
        first_correct = False
        for trial in range(trials):
            result = run_agent(
                question=query["question"],
                available_databases=query["available_databases"],
                schema_info=query["schema_info"],
            )
            valid, message = evaluator._validate_answer(query, result)
            if trial == 0:
                first_correct = bool(valid)
            if valid:
                total_trial_correct += 1
            total_trials += 1
            trials_report.append(
                {
                    "trial": trial + 1,
                    "correct": bool(valid),
                    "eval_correct": bool(valid),
                    "validation_message": message,
                    "status": result.get("status"),
                    "answer": result.get("answer"),
                    "confidence": result.get("confidence"),
                    "query_trace": result.get("query_trace", result.get("trace", [])),
                    "token_usage": result.get("token_usage", {}),
                    "used_databases": result.get("used_databases", []),
                }
            )

        if first_correct:
            total_first_correct += 1

        all_query_reports.append(
            {
                "id": query["id"],
                "question": query["question"],
                "first_trial_correct": first_correct,
                "trial_accuracy": round(sum(1 for item in trials_report if item["correct"]) / max(1, trials), 4),
                "trials": trials_report,
            }
        )

    total_queries = len(queries)
    pass_at_1 = round(total_first_correct / max(1, total_queries), 4)
    overall_trial_accuracy = round(total_trial_correct / max(1, total_trials), 4)
    dataset_label = f"DataAgentBench {dataset}"
    dataset_path = ROOT / "DataAgentBench"
    if dataset.lower().startswith("query_"):
        dataset_path = dataset_path / dataset
    else:
        dataset_path = dataset_path / f"query_{dataset}"

    results = {
        "dataset": dataset_label,
        "dataset_path": str(dataset_path),
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_queries": total_queries,
        "trials_per_query": trials,
        "correct_first_answers": total_first_correct,
        "correct_trials": total_trial_correct,
        "total_trials": total_trials,
        "pass@1": pass_at_1,
        "overall_trial_accuracy": overall_trial_accuracy,
        "queries": all_query_reports,
    }

    results_path = eval_root / "results.json"
    score_log_path = eval_root / "score_log.jsonl"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    score_entry = {
        "stage": "final",
        "dataset": dataset_label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_queries": total_queries,
        "trials_per_query": trials,
        "correct_first_answers": total_first_correct,
        "correct_trials": total_trial_correct,
        "total_trials": total_trials,
        "pass@1": pass_at_1,
        "overall_trial_accuracy": overall_trial_accuracy,
    }
    with score_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(score_entry, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "dataset": dataset,
                "total_queries": total_queries,
                "trials_per_query": trials,
                "pass@1": pass_at_1,
                "pass@1_counts": f"{total_first_correct}/{total_queries} queries with trial 1 correct",
                "overall_trial_accuracy": overall_trial_accuracy,
                "overall_trial_counts": f"{total_trial_correct}/{total_trials} trials correct",
                "note": "pass@1 and overall_trial_accuracy can match numerically when only some queries pass all trials; they measure different things.",
                "results_path": str(results_path),
                "score_log_path": str(score_log_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
