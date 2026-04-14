from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.main import run_agent
from agent.utils import wilson_interval


class OracleForgeEvaluator:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.logs_dir = self.repo_root / "eval"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_queries(self, queries: List[Dict[str, Any]]) -> Dict[str, Any]:
        per_query: List[Dict[str, Any]] = []
        passed = 0
        sentinel_log = self.logs_dir / "sentinel_trace.jsonl"
        for idx, query_case in enumerate(queries):
            question = query_case["question"]
            started = time.perf_counter()
            outcome = run_agent(
                question=question,
                available_databases=query_case.get("available_databases", ["postgresql", "mongodb"]),
                schema_info=query_case.get("schema_info", {}),
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            validation = self._validate_answer(query_case, outcome)
            correct = validation[0]
            if correct:
                passed += 1
            trace = outcome.get("query_trace", outcome.get("trace", []))
            per_query.append(
                {
                    "query_id": query_case.get("id", f"query_{idx}"),
                    "input_query": question,
                    "generated_query": outcome.get("predicted_queries", []),
                    "tool_calls": trace,
                    "execution_time_ms": duration_ms,
                    "result": outcome.get("answer"),
                    "correctness": "pass" if correct else "fail",
                    "validation_message": validation[1],
                    "failure_category": None if correct else self._classify_failure(query_case, outcome),
                    "architecture_disclosure": outcome.get("architecture_disclosure", {}),
                }
            )
            sentinel_payload = {
                "query_id": query_case.get("id", f"query_{idx}"),
                "tool_calls": [
                    {
                        "tool_used": event.get("tool_used"),
                        "raw_query": event.get("raw_query"),
                        "execution_time_ms": event.get("duration_ms"),
                        "success": event.get("success"),
                        "failure_type": event.get("failure_type"),
                        "merge_event": event.get("merge_event", False),
                        "merge_step": {
                            "left_key": event.get("left_key"),
                            "right_key": event.get("right_key"),
                            "rows_before": event.get("rows_before"),
                            "rows_after": event.get("rows_after"),
                        }
                        if event.get("merge_event")
                        else None,
                    }
                    for event in trace
                ],
                "final_status": outcome.get("status"),
                "answer": outcome.get("answer"),
                "confidence": outcome.get("confidence"),
            }
            with sentinel_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sentinel_payload, ensure_ascii=False) + "\n")
        total = len(per_query)
        pass_at_1 = (passed / total) if total else 0.0
        ci_low, ci_high = wilson_interval(passed, total)
        report = {
            "total_queries": total,
            "correct_queries": passed,
            "pass@1": round(pass_at_1, 4),
            "confidence_interval_95": [round(ci_low, 4), round(ci_high, 4)],
            "per_query_traces": per_query,
        }
        return report

    def evaluate_yelp_dataset(self) -> Dict[str, Any]:
        queries = self._load_dataagentbench_yelp_queries()
        return self.evaluate_queries(queries)

    def _load_dataagentbench_yelp_queries(self) -> List[Dict[str, Any]]:
        dab_root = self.repo_root / "DataAgentBench"
        queries: List[Dict[str, Any]] = []
        for query_dir in sorted(dab_root.glob("query*")):
            query_path = query_dir / "query.json"
            if not query_path.exists():
                continue
            text = json.loads(query_path.read_text(encoding="utf-8"))
            queries.append(
                {
                    "id": query_dir.name,
                    "question": text,
                    "available_databases": ["postgresql", "mongodb"],
                    "schema_info": {},
                    "validator_path": str(query_dir / "validate.py"),
                }
            )
        return queries

    def _validate_answer(self, query_case: Dict[str, Any], outcome: Dict[str, Any]) -> Tuple[bool, str]:
        validator_path = query_case.get("validator_path")
        if not validator_path:
            expected = query_case.get("expected", {})
            return self._validate_expected(expected, outcome.get("answer"))
        path = Path(validator_path)
        if not path.exists():
            return False, f"Validator missing: {validator_path}"
        ground_truth_path = path.parent / "ground_truth.csv"
        if ground_truth_path.exists():
            return self._validate_against_ground_truth(ground_truth_path, outcome.get("answer"))
        namespace: Dict[str, Any] = {}
        exec(path.read_text(encoding="utf-8"), namespace)
        validate_fn = namespace.get("validate")
        if not callable(validate_fn):
            return False, "Validator function not found."
        answer_text = self._stringify_answer(outcome.get("answer"))
        valid, message = validate_fn(answer_text)
        return bool(valid), str(message)

    def _validate_against_ground_truth(self, ground_truth_path: Path, actual: Any) -> Tuple[bool, str]:
        expected_raw = [line.strip() for line in ground_truth_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not expected_raw:
            return False, "Ground truth file empty."
        actual_norm = self._normalize_execution_output(actual)
        expected_norm = self._normalize_ground_truth(expected_raw)
        return actual_norm == expected_norm, f"execution_match={actual_norm == expected_norm}"

    def _normalize_execution_output(self, actual: Any) -> List[str]:
        if isinstance(actual, list):
            values = [self._norm_scalar(item) for item in actual]
            return sorted(values)
        if isinstance(actual, dict):
            values = [self._norm_scalar(v) for v in actual.values()]
            return sorted(values)
        text = self._stringify_answer(actual)
        return sorted([self._norm_scalar(item) for item in text.split(",") if item.strip()])

    def _normalize_ground_truth(self, rows: List[str]) -> List[str]:
        values: List[str] = []
        for row in rows:
            for token in row.split(","):
                cleaned = token.strip()
                if cleaned:
                    values.append(self._norm_scalar(cleaned))
        return sorted(values)

    @staticmethod
    def _norm_scalar(value: Any) -> str:
        text = str(value).strip()
        try:
            return f"{float(text):.2f}"
        except Exception:
            return text.lower()

    def _validate_expected(self, expected: Dict[str, Any], actual: Any) -> Tuple[bool, str]:
        expected_type = expected.get("type", "equals")
        expected_value = expected.get("value")
        if expected_type == "equals":
            return actual == expected_value, f"equals({expected_value})"
        if expected_type == "contains":
            ok = str(expected_value).lower() in str(actual).lower()
            return ok, f"contains({expected_value})"
        if expected_type == "min":
            try:
                ok = float(actual) >= float(expected_value)
                return ok, f"min({expected_value})"
            except (TypeError, ValueError):
                return False, "min-compare-failed"
        return False, "unsupported-expected-type"

    def _classify_failure(self, query_case: Dict[str, Any], outcome: Dict[str, Any]) -> str:
        used_dbs = {item.get("database") for item in outcome.get("used_databases", [])}
        question = query_case.get("question", "").lower()
        trace = outcome.get("trace", [])
        if len(used_dbs) < 2 and any(word in question for word in ["across", "join", "both"]):
            return "multi-database routing errors"
        if any(entry.get("failure_type") == "join_key_mismatch" for entry in trace):
            return "join/key mismatch errors"
        return "domain knowledge gaps"

    @staticmethod
    def _stringify_answer(answer: Any) -> str:
        if isinstance(answer, (dict, list)):
            return json.dumps(answer, ensure_ascii=False)
        return str(answer)


class LocalEvaluator:
    def __init__(self, queries_path: Path) -> None:
        self.queries_path = queries_path
        self.queries = self._load_queries(queries_path)
        self.evaluator = OracleForgeEvaluator()

    def _load_queries(self, path: Path) -> List[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload.get("queries", [])
        if isinstance(payload, list):
            return payload
        return []

    def evaluate(self) -> Dict[str, Any]:
        report = self.evaluator.evaluate_queries(self.queries)
        return {
            "total_queries": report["total_queries"],
            "correct_first_answers": report["correct_queries"],
            "pass@1": report["pass@1"],
            "confidence_interval_95": report["confidence_interval_95"],
            "results": report["per_query_traces"],
        }
