from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from utils.schema_introspection_tool import SchemaIntrospectionTool
from utils.token_limiter import TokenLimiter

from .context_builder import ContextBuilder
from .llm_reasoner import GroqLlamaReasoner
from .planner import QueryPlanner
from .sandbox_client import SandboxClient
from .tools_client import MCPToolsClient
from .utils import (
    compute_metrics,
    confidence_score,
    infer_join_key,
    join_records,
    sanitize_error,
)

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _merge_outputs(step_outputs: List[Dict[str, Any]], trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    successful_data = [entry.get("data", []) for entry in step_outputs if entry.get("ok")]
    normalized = [rows if isinstance(rows, list) else [] for rows in successful_data]
    if not normalized:
        return []
    merged = normalized[0]
    left_db = step_outputs[0].get("database", "postgresql")
    for idx, right_rows in enumerate(normalized[1:], start=1):
        left_key = infer_join_key(merged)
        right_key = infer_join_key(right_rows)
        if not left_key or not right_key:
            continue
        right_db = step_outputs[idx].get("database", "mongodb")
        joined = join_records(merged, right_rows, left_key, right_key, left_db=left_db, right_db=right_db)
        trace.append(
            {
                "merge_event": True,
                "left_key": left_key,
                "right_key": right_key,
                "rows_before": len(merged),
                "rows_after": len(joined),
                "join_resolver_used": "utils.join_key_resolver.JoinKeyResolver",
            }
        )
        merged = joined if joined else merged
        left_db = right_db
    return merged


def _answer_from_metrics(question: str, metrics: Dict[str, Any], records: List[Dict[str, Any]]) -> Any:
    text = question.lower()
    if "negative" in text and "sentiment" in text:
        return metrics["negative_sentiment_count"]
    if "high-value" in text and "ticket" in text:
        return metrics["high_value_with_tickets"]
    if "total sales" in text or "total revenue" in text:
        return metrics["total_sales"]
    if "how many" in text or "count" in text:
        return metrics["row_count"]
    return {"metrics": metrics, "records": records[:10]}


def _tool_payload(step: Dict[str, Any], question: str) -> Dict[str, Any]:
    payload = dict(step.get("query_payload", {}))
    payload["question"] = question
    payload["database"] = step.get("database")
    payload["dialect"] = step.get("dialect")
    return payload


def _record_runtime_corrections(question: str, plan: Dict[str, Any], tool_results: List[Dict[str, Any]]) -> None:
    failures = [item for item in tool_results if not item.get("ok")]
    if not failures:
        return
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "docs" / "driver_notes" / "runtime_corrections.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for failure in failures:
            payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "question": question,
                "failure_type": failure.get("error_type", "unknown_error"),
                "sanitized_error": sanitize_error(failure.get("error", "")),
                "tool": failure.get("tool"),
                "failed_query": failure.get("failed_query"),
                "plan_type": plan.get("plan_type"),
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _log_agent_run(payload: Dict[str, Any]) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "docs" / "driver_notes" / "agent_runtime_log.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_agent(question: str, available_databases: List[str], schema_info: Dict[str, Any]) -> Dict[str, Any]:
    trace: List[Dict[str, Any]] = []
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=True)
    token_limiter = TokenLimiter(
        max_prompt_tokens=int(os.getenv("MAX_PROMPT_TOKENS", "3500")),
        max_tool_loops=int(os.getenv("MAX_TOOL_LOOPS", "12")),
    )
    mock_mode = _env_bool("ORACLE_FORGE_MOCK_MODE", False)
    allow_mock_fallback = _env_bool("ORACLE_FORGE_ALLOW_MOCK_FALLBACK", False)
    tools = MCPToolsClient(
        base_url=os.getenv("MCP_BASE_URL", "http://localhost:5000"),
        mock_mode=mock_mode,
        allow_fallback_to_mock=allow_mock_fallback,
    )
    discovered_tools = tools.discover_tools()
    effective_mock_mode = tools.mock_mode
    discovered_schema = tools.get_schema_metadata()
    schema_metadata = SchemaIntrospectionTool().collect(discovered_schema)
    context = ContextBuilder().build(question, available_databases, schema_info, schema_metadata)
    context["context_layers"] = token_limiter.trim_context_layers(context.get("context_layers", {}))
    reasoner = GroqLlamaReasoner(repo_root=repo_root, token_limiter=token_limiter)
    llm_guidance = reasoner.plan(question=question, available_databases=available_databases, context=context)
    context["llm_guidance"] = {
        "selected_databases": llm_guidance.selected_databases,
        "rationale": llm_guidance.rationale,
        "query_hints": llm_guidance.query_hints,
        "model": llm_guidance.model,
        "used_llm": llm_guidance.used_llm,
    }
    planner = QueryPlanner(context)
    plan = planner.create_plan(question, available_databases)
    sandbox = SandboxClient(enabled=True)
    used_databases: List[Dict[str, str]] = []
    retries = 0
    tool_loop_counter = 0

    def _execute(step: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal tool_loop_counter
        tool_loop_counter += 1
        if not token_limiter.enforce_loop_limit(tool_loop_counter):
            return {
                "ok": False,
                "error": "Tool loop limit exceeded.",
                "error_type": "tool_routing_error",
                "tool": "",
                "failed_query": str(step.get("query_payload")),
            }
        tool_name = tools.select_tool(step.get("database", ""), step.get("dialect", "sql"))
        if not tool_name:
            return {
                "ok": False,
                "error": f"No compatible tool discovered for database: {step.get('database')}",
                "error_type": "tool_routing_error",
                "tool": "",
                "failed_query": str(step.get("query_payload")),
            }
        used_databases.append(
            {
                "database": step.get("database", ""),
                "reason": step.get("selection_reason", ""),
                "tool": tool_name,
            }
        )
        result = tools.execute_with_retry(
            tool_name=tool_name,
            payload=_tool_payload(step, question),
            selection_reason=step.get("selection_reason", ""),
            dialect_handling=step.get("dialect", "sql"),
            trace=trace,
            max_retries=2,
        )
        result["database"] = step.get("database")
        return result

    closed_loop = planner.execute_closed_loop(
        question=question,
        available_databases=available_databases,
        step_executor=_execute,
        max_replans=min(2, max(0, token_limiter.max_tool_loops // 3)),
    )
    attempts = closed_loop["attempts"]
    latest_attempt = attempts[-1] if attempts else {"plan": plan, "results": []}
    plan = latest_attempt["plan"]
    sandbox_outcome = sandbox.execute_plan(plan, _execute) if not latest_attempt["results"] else {
        "result": latest_attempt["results"],
        "trace": [{"sandbox_mode": "simulated", "steps_executed": len(latest_attempt["results"])}],
        "validation_status": {
            "valid": all(item.get("ok") for item in latest_attempt["results"]),
            "failed_steps": [i + 1 for i, item in enumerate(latest_attempt["results"]) if not item.get("ok")],
        },
    }
    tool_results = sandbox_outcome["result"]
    _record_runtime_corrections(question, plan, tool_results)
    retries = sum(max(0, int(item.get("attempts", 1)) - 1) for item in tool_results)
    successful_steps = sum(1 for item in tool_results if item.get("ok"))
    predicted_queries = [
        {
            "database": step.get("database"),
            "dialect": step.get("dialect"),
            "query": step.get("query_payload", {}).get("sql", step.get("query_payload", {}).get("pipeline")),
        }
        for step in plan.get("steps", [])
    ]

    if successful_steps == 0:
        safe_errors = [sanitize_error(item.get("error", "")) for item in tool_results if not item.get("ok")]
        response = {
            "status": "failure",
            "question": question,
            "answer": None,
            "confidence": confidence_score(
                total_steps=max(1, len(plan.get("steps", []))),
                successful_steps=0,
                retries=retries,
                explicit_failure=True,
                used_mock_mode=effective_mock_mode,
            ),
            "trace": trace,
            "query_trace": trace,
            "plan": plan,
            "used_databases": used_databases,
            "validation_status": sandbox_outcome["validation_status"],
            "error": "Safe failure: unable to complete query after bounded retries.",
            "error_summary": safe_errors,
            "predicted_queries": predicted_queries,
            "architecture_disclosure": {
                "mcp_tools_used": [entry.get("tool") for entry in used_databases],
                "kb_layers_accessed": ["v1_architecture", "v2_domain", "v3_corrections"],
                "llm_model": llm_guidance.model,
                "llm_used_for_reasoning": llm_guidance.used_llm,
                "confidence_score": confidence_score(
                    total_steps=max(1, len(plan.get("steps", []))),
                    successful_steps=0,
                    retries=retries,
                    explicit_failure=True,
                    used_mock_mode=effective_mock_mode,
                ),
            },
            "token_usage": token_limiter.usage_entry(
                prompt_text=json.dumps({"question": question, "context": context.get("context_layers", {})}, ensure_ascii=False),
                completion_text=json.dumps({"trace": trace}, ensure_ascii=False),
            ),
        }
        _log_agent_run(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "question": question,
                "status": response["status"],
                "confidence": response["confidence"],
                "used_databases": response["used_databases"],
                "architecture_disclosure": response["architecture_disclosure"],
            }
        )
        return response

    merged_records = _merge_outputs(tool_results, trace)
    metrics = compute_metrics(merged_records)
    answer = _answer_from_metrics(question, metrics, merged_records)
    explicit_failure = not sandbox_outcome["validation_status"]["valid"]
    confidence = confidence_score(
        total_steps=max(1, len(plan.get("steps", []))),
        successful_steps=successful_steps,
        retries=retries,
        explicit_failure=explicit_failure,
        used_mock_mode=effective_mock_mode,
    )
    response = {
        "status": "success" if not explicit_failure else "partial_success",
        "question": question,
        "answer": answer,
        "metrics": metrics,
        "confidence": confidence,
        "trace": trace,
        "query_trace": trace,
        "plan": plan,
        "tools_discovered_count": len(discovered_tools),
        "used_databases": used_databases,
        "validation_status": sandbox_outcome["validation_status"],
        "mock_mode": effective_mock_mode,
        "predicted_queries": predicted_queries,
        "architecture_disclosure": {
            "mcp_tools_used": [entry.get("tool") for entry in used_databases],
            "kb_layers_accessed": ["v1_architecture", "v2_domain", "v3_corrections"],
            "llm_model": llm_guidance.model,
            "llm_used_for_reasoning": llm_guidance.used_llm,
            "confidence_score": confidence,
        },
        "context_layers_used": list(context.get("context_layers", {}).keys()),
        "token_usage": token_limiter.usage_entry(
            prompt_text=json.dumps({"question": question, "context": context.get("context_layers", {})}, ensure_ascii=False),
            completion_text=json.dumps({"trace": trace, "answer": answer}, ensure_ascii=False),
        ),
    }
    _log_agent_run(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "status": response["status"],
            "confidence": response["confidence"],
            "used_databases": response["used_databases"],
            "architecture_disclosure": response["architecture_disclosure"],
        }
    )
    return response


def run_agent_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = str(payload.get("question", ""))
    available_databases = payload.get("available_databases", ["postgresql", "mongodb", "sqlite", "duckdb"])
    schema_info = payload.get("schema_info", {})
    result = run_agent(question=question, available_databases=available_databases, schema_info=schema_info)
    return {
        "answer": result.get("answer"),
        "query_trace": result.get("query_trace", result.get("trace", [])),
        "confidence": result.get("confidence", 0.0),
        "status": result.get("status"),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Oracle Forge agent runner")
    parser.add_argument("--question", required=True, help="Natural language question")
    parser.add_argument(
        "--dbs",
        default="postgresql,mongodb,sqlite,duckdb",
        help="Comma-separated available database names",
    )
    args = parser.parse_args()
    databases = [item.strip() for item in args.dbs.split(",") if item.strip()]
    result = run_agent(args.question, databases, {})
    print(result)


if __name__ == "__main__":
    main()
