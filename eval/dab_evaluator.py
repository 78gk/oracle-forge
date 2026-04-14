from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent.main import run_agent
from agent.utils import wilson_interval


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _is_correct(expected: Dict[str, Any], actual: Any) -> bool:
    expected_type = expected.get("type", "equals")
    expected_value = expected.get("value")
    if expected_type == "equals":
        return _normalize_scalar(actual) == _normalize_scalar(expected_value)
    if expected_type == "contains":
        return str(expected_value).lower() in str(actual).lower()
    if expected_type == "min":
        try:
            return float(actual) >= float(expected_value)
        except (TypeError, ValueError):
            return False
    if expected_type == "one_of":
        options = [_normalize_scalar(item) for item in expected_value]
        return _normalize_scalar(actual) in options
    return False


class DABEvaluator:
    def __init__(self, dataset_path: Path, trials_per_query: int = 50) -> None:
        self.dataset_path = dataset_path
        self.trials_per_query = trials_per_query
        self.dataset = self._load_dataset(dataset_path)

    @staticmethod
    def _load_dataset(path: Path) -> List[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            queries = payload.get("queries", [])
            return queries if isinstance(queries, list) else []
        return payload if isinstance(payload, list) else []

    def evaluate(self) -> Dict[str, Any]:
        query_reports: List[Dict[str, Any]] = []
        pass1_count = 0
        total_trials = 0
        total_trial_correct = 0
        active_db_types = set()
        for query in self.dataset:
            trial_reports: List[Dict[str, Any]] = []
            first_correct = False
            for trial in range(self.trials_per_query):
                result = run_agent(
                    question=query["question"],
                    available_databases=query.get("available_databases", ["postgresql", "mongodb"]),
                    schema_info=query.get("schema_info", {}),
                )
                correct = _is_correct(query["expected"], result.get("answer"))
                if trial == 0:
                    first_correct = correct
                total_trials += 1
                total_trial_correct += 1 if correct else 0
                for used in result.get("used_databases", []):
                    active_db_types.add(used.get("database"))
                trial_reports.append(
                    {
                        "trial": trial + 1,
                        "correct": correct,
                        "status": result.get("status"),
                        "answer": result.get("answer"),
                        "confidence": result.get("confidence"),
                        "trace": result.get("trace", []),
                        "used_databases": result.get("used_databases", []),
                        "predicted_queries": result.get("predicted_queries", []),
                    }
                )
            pass1_count += 1 if first_correct else 0
            query_reports.append(
                {
                    "id": query["id"],
                    "question": query["question"],
                    "expected": query["expected"],
                    "first_trial_correct": first_correct,
                    "trial_accuracy": round(sum(1 for item in trial_reports if item["correct"]) / self.trials_per_query, 4),
                    "trials": trial_reports,
                }
            )
        total_queries = len(self.dataset)
        pass_at_1 = pass1_count / total_queries if total_queries else 0.0
        ci_low, ci_high = wilson_interval(pass1_count, total_queries)
        overall_trial_accuracy = total_trial_correct / total_trials if total_trials else 0.0
        return {
            "dataset_path": str(self.dataset_path),
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_queries": total_queries,
            "trials_per_query": self.trials_per_query,
            "correct_first_answers": pass1_count,
            "pass@1": round(pass_at_1, 4),
            "pass@1_ci95": [round(ci_low, 4), round(ci_high, 4)],
            "overall_trial_accuracy": round(overall_trial_accuracy, 4),
            "connected_db_count": len(active_db_types),
            "active_db_types": sorted(item for item in active_db_types if item),
            "queries": query_reports,
        }


def run_regression_suite(dataset_path: Path) -> Dict[str, Any]:
    evaluator = DABEvaluator(dataset_path=dataset_path, trials_per_query=1)
    result = evaluator.evaluate()
    failures = []
    for query in result["queries"]:
        if not query["first_trial_correct"]:
            failures.append({"id": query["id"], "question": query["question"]})
    result["regression_pass"] = len(failures) == 0
    result["failures"] = failures
    return result


def run_probes(dataset_path: Path) -> Dict[str, Any]:
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    probes = payload.get("probes", payload if isinstance(payload, list) else [])
    reports: List[Dict[str, Any]] = []
    categories = set()
    for probe in probes:
        categories.add(probe.get("category", "unknown"))
        result = run_agent(
            question=probe["question"],
            available_databases=probe.get("available_databases", ["postgresql", "mongodb"]),
            schema_info=probe.get("schema_info", {}),
        )
        check = probe.get("check", {})
        ok = _evaluate_probe_check(check, result)
        reports.append(
            {
                "id": probe["id"],
                "category": probe.get("category"),
                "expected_failure_mode": probe.get("expected_failure_mode"),
                "passed": ok,
                "status": result.get("status"),
                "answer": result.get("answer"),
                "trace": result.get("trace", []),
                "used_databases": result.get("used_databases", []),
            }
        )
    passed = sum(1 for item in reports if item["passed"])
    return {
        "probe_count": len(probes),
        "categories": sorted(categories),
        "passed_probes": passed,
        "probe_validity": "PASS" if len(probes) >= 15 and len(categories) >= 3 and passed == len(probes) else "FAIL",
        "results": reports,
    }


def _evaluate_probe_check(check: Dict[str, Any], result: Dict[str, Any]) -> bool:
    check_type = check.get("type")
    if check_type == "answer_equals":
        return _normalize_scalar(result.get("answer")) == _normalize_scalar(check.get("value"))
    if check_type == "status_equals":
        return result.get("status") == check.get("value")
    if check_type == "used_dbs_contains":
        expected = set(check.get("value", []))
        used = {item.get("database") for item in result.get("used_databases", [])}
        return expected.issubset(used)
    if check_type == "failure_type":
        expected = check.get("value")
        observed = [entry.get("failure_type") for entry in result.get("trace", []) if entry.get("failure_type")]
        return expected in observed
    return False


def append_score_log(score_log_path: Path, stage: str, summary: Dict[str, Any]) -> None:
    score_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "stage": stage,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_queries": summary.get("total_queries"),
        "trials_per_query": summary.get("trials_per_query"),
        "pass@1": summary.get("pass@1"),
        "overall_trial_accuracy": summary.get("overall_trial_accuracy"),
        "connected_db_count": summary.get("connected_db_count"),
        "active_db_types": summary.get("active_db_types"),
    }
    with score_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def compute_progression(score_log_path: Path) -> Dict[str, Any]:
    if not score_log_path.exists():
        return {"baseline_exists": False, "final_run_exists": False, "improvement_log": False}
    entries = []
    for line in score_log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    baseline = next((item for item in entries if item.get("stage") == "baseline"), None)
    final = next((item for item in reversed(entries) if item.get("stage") == "final"), None)
    improvement = None
    if baseline and final and baseline.get("pass@1") is not None and final.get("pass@1") is not None:
        improvement = round(float(final["pass@1"]) - float(baseline["pass@1"]), 4)
    return {
        "baseline_exists": baseline is not None,
        "final_run_exists": final is not None,
        "improvement_log": improvement is not None,
        "baseline_pass@1": baseline.get("pass@1") if baseline else None,
        "final_pass@1": final.get("pass@1") if final else None,
        "pass@1_delta": improvement,
    }
