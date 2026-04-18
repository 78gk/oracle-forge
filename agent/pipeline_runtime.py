"""
Oracle Forge agent pipeline: phased execution used by sequential ``run_agent`` and LangGraph conductor.

Toolbox (MCP) and planner behavior match ``agent.main`` prior to extraction.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from utils.dataset_isolation import DatasetIsolationError, isolation_enabled, validate_routing_selected_tables
from utils.dataset_profiles import DatasetProfile
from utils.execution_merge_log import append_execution_merge_log, truncate_tool_preview
from utils.question_plan_alignment import plan_aligns_with_question
from utils.schema_column_enricher import enrich_schema_metadata_columns, rebuild_schema_bundle_context
from utils.schema_introspection_tool import SchemaIntrospectionTool
from utils.schema_registry.routing_compact import load_registry_json_optional
from utils.token_limiter import TokenLimiter

from .context_builder import ContextBuilder
from .global_planner import GlobalPlannerFailed, global_planner_enabled, global_planner_strict, run_global_plan
from .llm_reasoner import LLMRoutingFailed, OpenRouterRoutingReasoner
from .planner import QueryPlanner
from .sandbox_client import SandboxClient
from .tools_client import MCPToolsClient
from .query_safety import validate_step_payload
from .utils import (
    compute_metrics,
    confidence_score,
    sanitize_error,
)

# Deferred imports from agent.main (helpers + response builders) to avoid import cycles at module load.
def _main():
    from agent import main as main_mod

    return main_mod


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class OracleForgePipeline:
    """Mutable pipeline state for phased LangGraph nodes and linear ``run_sequential``."""

    def __init__(
        self,
        *,
        question: str,
        routing_question: str,
        available_databases: List[str],
        schema_info: Dict[str, Any],
        dataset_id: Optional[str],
        repo_root: Path,
        profile: Optional[DatasetProfile],
        duck_for_tools: Optional[str],
    ) -> None:
        self.question = question
        self.routing_question = routing_question
        self.available_databases = available_databases
        self.schema_info = schema_info
        self.dataset_id = dataset_id
        self.repo_root = repo_root
        self.profile = profile
        self.duck_for_tools = duck_for_tools

        self.trace: List[Dict[str, Any]] = []
        self.token_limiter: Optional[TokenLimiter] = None
        self.tools: Optional[MCPToolsClient] = None
        self.discovered_tools: List[Dict[str, Any]] = []
        self.effective_mock_mode = False
        self.context: Dict[str, Any] = {}
        self.schema_metadata: Dict[str, Any] = {}
        self.llm_guidance: Any = None
        self.planner: Optional[QueryPlanner] = None
        self.reasoner: Optional[OpenRouterRoutingReasoner] = None

    def phase_setup(self) -> Optional[Dict[str, Any]]:
        M = _main()
        load_dotenv(self.repo_root / ".env", override=False)
        self.token_limiter = TokenLimiter(
            max_prompt_tokens=int(os.getenv("MAX_PROMPT_TOKENS", "3500")),
            max_tool_loops=int(os.getenv("MAX_TOOL_LOOPS", "12")),
        )
        assert self.token_limiter is not None
        mock_mode = _env_bool("ORACLE_FORGE_MOCK_MODE", False)
        allow_mock_fallback = _env_bool("ORACLE_FORGE_ALLOW_MOCK_FALLBACK", False)
        self.tools = MCPToolsClient(
            base_url=os.getenv("MCP_BASE_URL", "http://localhost:5000"),
            mock_mode=mock_mode,
            allow_fallback_to_mock=allow_mock_fallback,
            duckdb_path=self.duck_for_tools,
        )
        self.discovered_tools = self.tools.discover_tools()
        self.effective_mock_mode = self.tools.mock_mode
        discovered_schema = self.tools.get_schema_metadata()
        schema_metadata = SchemaIntrospectionTool().collect(discovered_schema)
        try:
            context = ContextBuilder().build(
                self.question,
                self.available_databases,
                self.schema_info,
                schema_metadata,
                dataset_id=self.dataset_id,
            )
        except DatasetIsolationError as exc:
            return M._dataset_isolation_response(
                question=self.question,
                dataset_id=self.dataset_id,
                exc=exc,
                trace=self.trace,
                token_limiter=self.token_limiter,
                effective_mock_mode=self.effective_mock_mode,
                tools_discovered_count=len(self.discovered_tools),
            )
        context["context_layers"] = self.token_limiter.trim_context_layers(context.get("context_layers", {}))
        context["routing_question"] = self.routing_question
        context["user_question"] = self.question
        self.context = context
        self.schema_metadata = schema_metadata
        self.reasoner = OpenRouterRoutingReasoner(repo_root=self.repo_root, token_limiter=self.token_limiter)
        return None

    def phase_route(self) -> Optional[Dict[str, Any]]:
        M = _main()
        assert self.reasoner is not None and self.token_limiter is not None and self.tools is not None
        try:
            llm_guidance = self.reasoner.plan(
                question=self.routing_question,
                available_databases=self.available_databases,
                context=self.context,
            )
        except LLMRoutingFailed as exc:
            return M._routing_failure_response(
                question=self.question,
                dataset_id=self.dataset_id,
                error_message=str(exc),
                trace=self.trace,
                token_limiter=self.token_limiter,
                effective_mock_mode=self.effective_mock_mode,
                tools_discovered_count=len(self.discovered_tools),
            )
        except DatasetIsolationError as exc:
            return M._dataset_isolation_response(
                question=self.question,
                dataset_id=self.dataset_id,
                exc=exc,
                trace=self.trace,
                token_limiter=self.token_limiter,
                effective_mock_mode=self.effective_mock_mode,
                tools_discovered_count=len(self.discovered_tools),
            )
        self.context["llm_guidance"] = {
            "selected_databases": llm_guidance.selected_databases,
            "selected_tables": getattr(llm_guidance, "selected_tables", None) or {},
            "rationale": llm_guidance.rationale,
            "query_hints": llm_guidance.query_hints,
            "model": llm_guidance.model,
            "used_llm": llm_guidance.used_llm,
        }
        self.llm_guidance = llm_guidance
        return None

    def phase_schema_and_global_plan(self) -> Optional[Dict[str, Any]]:
        M = _main()
        assert self.llm_guidance is not None and self.token_limiter is not None and self.tools is not None
        mongo_db = (os.getenv("MONGODB_DATABASE") or "yelp_db").strip()
        if self.profile and self.profile.mongodb_database:
            mongo_db = self.profile.mongodb_database.strip() or mongo_db
        sqlite_env = (os.getenv("SQLITE_PATH") or "").strip()
        duck_env = (self.duck_for_tools or os.getenv("DUCKDB_PATH") or "").strip()
        selected_for_enrich = self.llm_guidance.selected_databases or self.available_databases
        self.schema_metadata = enrich_schema_metadata_columns(
            self.schema_metadata,
            selected_for_enrich,
            repo_root=self.repo_root,
            postgres_dsn=os.getenv("POSTGRES_DSN"),
            sqlite_path=sqlite_env,
            duckdb_path=duck_env,
            mongo_uri=os.getenv("MONGODB_URI"),
            mongo_database=mongo_db,
        )
        self.context["schema_metadata"] = self.schema_metadata
        try:
            rebuild_schema_bundle_context(
                self.context, self.available_databases, self.dataset_id, repo_root=self.repo_root
            )
        except DatasetIsolationError as exc:
            return M._dataset_isolation_response(
                question=self.question,
                dataset_id=self.dataset_id,
                exc=exc,
                trace=self.trace,
                token_limiter=self.token_limiter,
                effective_mock_mode=self.effective_mock_mode,
                tools_discovered_count=len(self.discovered_tools),
            )
        rid = (
            str(self.dataset_id).strip()
            if isinstance(self.dataset_id, str) and str(self.dataset_id).strip()
            else ""
        )
        if rid and global_planner_enabled():
            reg_gp = load_registry_json_optional(self.repo_root, rid)
            gp: Optional[Dict[str, Any]] = None
            try:
                gp = run_global_plan(
                    repo_root=self.repo_root,
                    question=self.question,
                    routing_question=self.routing_question,
                    context=self.context,
                    available_databases=self.available_databases,
                )
            except GlobalPlannerFailed as exc:
                if global_planner_strict():
                    return M._global_planner_failure_response(
                        question=self.question,
                        dataset_id=self.dataset_id,
                        error_message=str(exc),
                        trace=self.trace,
                        token_limiter=self.token_limiter,
                        effective_mock_mode=self.effective_mock_mode,
                        tools_discovered_count=len(self.discovered_tools),
                    )
                gp = None
            if isinstance(gp, dict) and not gp.get("_degraded"):
                if reg_gp and isolation_enabled():
                    try:
                        validate_routing_selected_tables(
                            reg_gp,
                            gp.get("selected_tables"),
                            self.available_databases,
                            dataset_id=rid,
                            phase="global_plan",
                            source="global_planner.selected_tables",
                        )
                    except DatasetIsolationError as exc:
                        return M._dataset_isolation_response(
                            question=self.question,
                            dataset_id=self.dataset_id,
                            exc=exc,
                            trace=self.trace,
                            token_limiter=self.token_limiter,
                            effective_mock_mode=self.effective_mock_mode,
                            tools_discovered_count=len(self.discovered_tools),
                        )
                self.context["global_plan"] = gp
        self.planner = QueryPlanner(self.context)
        return None

    def phase_execute_and_merge(self) -> Dict[str, Any]:
        M = _main()
        assert (
            self.planner is not None
            and self.tools is not None
            and self.token_limiter is not None
            and self.llm_guidance is not None
        )
        tools = self.tools
        token_limiter = self.token_limiter
        question = self.question
        routing_question = self.routing_question
        schema_metadata = self.schema_metadata
        trace = self.trace
        llm_guidance = self.llm_guidance
        repo_root = self.repo_root
        dataset_id = self.dataset_id
        available_databases = self.available_databases
        planner = self.planner

        plan: Dict[str, Any] = {}
        sandbox = SandboxClient(enabled=True)
        used_databases: List[Dict[str, str]] = []
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
            safe_ok, safe_msg = validate_step_payload(step, schema_metadata)
            if not safe_ok:
                return {
                    "ok": False,
                    "error": f"Query validation failed: {safe_msg}",
                    "error_type": "unsafe_sql",
                    "tool": tool_name,
                    "failed_query": str(step.get("query_payload")),
                }
            result = tools.execute_with_retry(
                tool_name=tool_name,
                payload=M._tool_payload(step, question),
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
            routing_question=routing_question,
        )
        loop_meta = M._closed_loop_summary(closed_loop)
        trace.append(
            {
                "event": "closed_loop",
                "closed_loop_ok": loop_meta["ok"],
                "attempt_count": loop_meta["attempt_count"],
                "replans": loop_meta["replans"],
                "attempts": loop_meta["attempts"],
            }
        )
        attempts = closed_loop["attempts"]
        latest_attempt = attempts[-1] if attempts else {"plan": plan, "results": []}
        plan = latest_attempt["plan"]
        sandbox_outcome = (
            sandbox.execute_plan(plan, _execute)
            if not latest_attempt["results"]
            else {
                "result": latest_attempt["results"],
                "trace": [{"sandbox_mode": "simulated", "steps_executed": len(latest_attempt["results"])}],
                "validation_status": {
                    "valid": all(item.get("ok") for item in latest_attempt["results"]),
                    "failed_steps": [
                        i + 1
                        for i, item in enumerate(latest_attempt["results"])
                        if not item.get("ok")
                    ],
                },
            }
        )
        tool_results = sandbox_outcome["result"]
        M._record_runtime_corrections(question, plan, tool_results)
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
            gate_fail = bool(plan.get("schema_gate_failed"))
            err_msg = (
                str(plan.get("gate_detail") or "need_schema_refresh")
                if gate_fail
                else "Safe failure: unable to complete query after bounded retries."
            )
            err_type = "need_schema_refresh" if gate_fail else None
            response = {
                "status": "failure",
                "question": question,
                "dataset_id": dataset_id,
                "answer": None,
                "closed_loop": loop_meta,
                "confidence": confidence_score(
                    total_steps=max(1, len(plan.get("steps", []))),
                    successful_steps=0,
                    retries=retries,
                    explicit_failure=True,
                    used_mock_mode=self.effective_mock_mode,
                ),
                "trace": trace,
                "query_trace": trace,
                "plan": plan,
                "used_databases": used_databases,
                "validation_status": sandbox_outcome["validation_status"],
                "error": err_msg,
                "error_type": err_type,
                "error_summary": safe_errors,
                "predicted_queries": predicted_queries,
                "database_results": [],
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
                        used_mock_mode=self.effective_mock_mode,
                    ),
                },
                "token_usage": token_limiter.usage_entry(
                    prompt_text=json.dumps(
                        {"question": question, "context": self.context.get("context_layers", {})},
                        ensure_ascii=False,
                    ),
                    completion_text=json.dumps({"trace": trace}, ensure_ascii=False),
                ),
            }
            M._log_agent_run(
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

        merged_records = M._merge_outputs(tool_results, trace)
        metrics = compute_metrics(merged_records)
        answer = M._answer_from_metrics(question, metrics, merged_records)
        answer = M._shape_answer_for_eval(answer, merged_records, question)

        merge_strategies = [e for e in trace if isinstance(e, dict) and e.get("merge_strategy")]
        append_execution_merge_log(
            repo_root,
            {
                "question": question[:2000],
                "dataset_id": dataset_id,
                "merge_strategy_events": merge_strategies[-5:],
                "tool_results_summary": truncate_tool_preview(
                    [
                        {
                            "ok": x.get("ok"),
                            "database": x.get("database"),
                            "error_type": x.get("error_type"),
                            "row_count": len(x.get("data", [])) if isinstance(x.get("data"), list) else None,
                        }
                        for x in tool_results
                    ],
                    max_chars=8000,
                ),
                "shaped_answer_preview": truncate_tool_preview(answer, max_chars=6000),
            },
        )
        align_ok, align_reason = plan_aligns_with_question(
            question, plan, dataset_playbook=self.context.get("dataset_playbook")
        )
        explicit_failure = not sandbox_outcome["validation_status"]["valid"] or not align_ok
        confidence = confidence_score(
            total_steps=max(1, len(plan.get("steps", []))),
            successful_steps=successful_steps,
            retries=retries,
            explicit_failure=explicit_failure,
            used_mock_mode=self.effective_mock_mode,
        )
        merge_info = next(
            (e for e in reversed(trace) if isinstance(e, dict) and e.get("merge_strategy")),
            None,
        )
        database_results: List[Dict[str, Any]] = []
        for r in tool_results:
            if not r.get("ok"):
                continue
            data = r.get("data")
            database_results.append(
                {
                    "database": r.get("database"),
                    "row_count": len(data) if isinstance(data, list) else None,
                    "rows": data,
                }
            )
        response = {
            "status": "success" if not explicit_failure else "failure",
            "question": question,
            "dataset_id": dataset_id,
            "merge_info": merge_info,
            "answer": answer,
            "database_results": database_results,
            "closed_loop": loop_meta,
            "metrics": metrics,
            "confidence": confidence,
            "trace": trace,
            "query_trace": trace,
            "plan": plan,
            "tools_discovered_count": len(self.discovered_tools),
            "used_databases": used_databases,
            "validation_status": {
                **sandbox_outcome["validation_status"],
                "semantic_ok": align_ok,
                "semantic_reason": align_reason or None,
            },
            "semantic_alignment": {"ok": align_ok, "reason": align_reason or None},
            "error": ((align_reason or "semantic_mismatch") if successful_steps > 0 and not align_ok else None),
            "error_type": (("semantic_mismatch" if not align_ok else None) if successful_steps > 0 else None),
            "mock_mode": self.effective_mock_mode,
            "predicted_queries": predicted_queries,
            "architecture_disclosure": {
                "mcp_tools_used": [entry.get("tool") for entry in used_databases],
                "kb_layers_accessed": ["v1_architecture", "v2_domain", "v3_corrections"],
                "llm_model": llm_guidance.model,
                "llm_used_for_reasoning": llm_guidance.used_llm,
                "confidence_score": confidence,
            },
            "context_layers_used": list(self.context.get("context_layers", {}).keys()),
            "token_usage": token_limiter.usage_entry(
                prompt_text=json.dumps(
                    {"question": question, "context": self.context.get("context_layers", {})},
                    ensure_ascii=False,
                ),
                completion_text=json.dumps({"trace": trace, "answer": answer}, ensure_ascii=False),
            ),
        }
        M._log_agent_run(
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

    def run_sequential(self) -> Dict[str, Any]:
        r = self.phase_setup()
        if r is not None:
            return r
        r = self.phase_route()
        if r is not None:
            return r
        r = self.phase_schema_and_global_plan()
        if r is not None:
            return r
        return self.phase_execute_and_merge()


def dispatch_agent_run(
    question: str,
    routing_question: str,
    available_databases: List[str],
    schema_info: Dict[str, Any],
    dataset_id: Optional[str],
    profile: Optional[DatasetProfile],
    duck_for_tools: Optional[str],
) -> Dict[str, Any]:
    """Entry used from ``main.run_agent`` after profile env is pushed."""
    repo_root = Path(__file__).resolve().parents[1]
    pipe = OracleForgePipeline(
        question=question,
        routing_question=routing_question,
        available_databases=available_databases,
        schema_info=schema_info,
        dataset_id=dataset_id,
        repo_root=repo_root,
        profile=profile,
        duck_for_tools=duck_for_tools,
    )
    use_graph = _env_bool("ORACLE_FORGE_USE_LANGGRAPH", True)
    if not use_graph:
        return pipe.run_sequential()
    try:
        from .conductor import run_with_langgraph

        return run_with_langgraph(pipe)
    except ImportError:
        return pipe.run_sequential()
