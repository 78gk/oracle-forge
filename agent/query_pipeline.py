"""
Query pipeline — four explicit phases (orchestrated by ``LLMQueryGenerator`` + ``QueryPlanner`` + ``main``):

1. **Planner** — NL → :class:`AnswerContract` (heuristic ``build_answer_contract`` or optional LLM).
2. **Schema linker** — scoped engine tables/collections → :class:`LinkedSchemaPayload` (readiness gate + compact JSON).
3. **Query generator** — LLM emits SQL / Mongo pipeline using only contract + linked schema.
4. **Semantic linter** — ``semantic_lint_plan`` / ``plan_aligns_with_question`` on the executed plan (in ``main``).

Testing: enable ``ORACLE_FORGE_LLM_PLANNER`` for an extra planner LLM call; inspect ``pipeline_trace`` /
``pipeline_metadata`` on generator output and ``plan["query_pipeline"]`` in the agent response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple

import json


def _has_year_token(q: str) -> bool:
    return bool(re.search(r"\b20\d{2}\b", q))


PlannerBackend = Literal["heuristic", "llm"]


@dataclass
class AnswerContract:
    """Expected shape of the answer (prompt contract, not execution)."""

    summary: str
    output_grain: str  # e.g. "scalar", "one_row_multi_column", "per_group"
    metrics: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    time_bounds: List[str] = field(default_factory=list)
    requires_join_or_group: bool = False


@dataclass
class LinkedSchemaPayload:
    """Phase 2 output: gated, compact schema slice for one engine."""

    engine: str
    scoped_names: List[str]
    linked_schema_json: str
    readiness_ok: bool
    readiness_message: str = ""


class SemanticLinter(Protocol):
    def __call__(
        self,
        question: str,
        plan: Dict[str, Any],
        *,
        dataset_playbook: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]: ...


def semantic_lint_plan(
    question: str,
    plan: Dict[str, Any],
    *,
    dataset_playbook: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Delegate to ``plan_aligns_with_question`` (semantic pass / fail)."""
    from utils.question_plan_alignment import plan_aligns_with_question

    return plan_aligns_with_question(question, plan, dataset_playbook=dataset_playbook)


def build_answer_contract(question: str, dataset_id: Optional[str] = None) -> AnswerContract:
    """
    Lightweight planner output without an extra LLM call.
    Refine over time or replace with structured LLM planner.
    """
    q = (question or "").strip().lower()
    metrics: List[str] = []
    filters = []
    dims = []
    time_bounds = []
    requires_jg = False
    if "average" in q or "avg" in q or "mean" in q:
        metrics.append("average")
    if "count" in q or "how many" in q:
        metrics.append("count")
    if "state" in q or "u.s." in q:
        dims.append("region/state")
        requires_jg = True
    if "during" in q or _has_year_token(q):
        time_bounds.append("time_window")
    if "parking" in q:
        filters.append("parking_offer")
    grain = "one_row_multi_column" if ("which " in q and " and " in q) or len(metrics) > 1 else "scalar"
    if dims or "group" in q or "per " in q:
        requires_jg = True
        grain = "per_group"
    summary = f"Answer contract: metrics={metrics or ['unspecified']}; dims={dims}; filters={filters}; grain={grain}"
    return AnswerContract(
        summary=summary,
        output_grain=grain,
        metrics=metrics,
        filters=filters,
        dimensions=dims,
        time_bounds=time_bounds,
        requires_join_or_group=requires_jg,
    )


def contract_to_prompt_json(contract: AnswerContract) -> str:
    return json.dumps(
        {
            "output_grain": contract.output_grain,
            "metrics": contract.metrics,
            "filters": contract.filters,
            "dimensions": contract.dimensions,
            "time_bounds": contract.time_bounds,
            "requires_join_or_group": contract.requires_join_or_group,
        },
        ensure_ascii=False,
    )


def linked_schema_compact(scoped_schema: Dict[str, Any], *, max_chars: int = 8000) -> str:
    """Trimmed JSON of scoped schema for prompts (actual columns only)."""
    raw = json.dumps(scoped_schema, ensure_ascii=False, indent=2)
    return raw[:max_chars]


def phase_schema_link(
    engine: str,
    scoped_table_or_collection_names: List[str],
    scoped_engine_dict: Dict[str, Any],
    schema_metadata: Dict[str, Any],
    *,
    max_json_chars: int = 10000,
) -> Tuple[Optional[LinkedSchemaPayload], str]:
    """
    Phase 2 — readiness gate + linked JSON for prompts.

    Returns ``(payload, "")`` when gate passes; ``(None, need_schema_refresh:...)`` otherwise.
    """
    from utils.schema_readiness import schema_gate_mongo_collections, schema_gate_sql_tables

    db = engine.strip().lower()
    names = list(scoped_table_or_collection_names)
    if db == "mongodb":
        ok, msg = schema_gate_mongo_collections(db, schema_metadata, names)
    else:
        ok, msg = schema_gate_sql_tables(db, schema_metadata, names)
    if not ok:
        return None, msg
    js = linked_schema_compact(scoped_engine_dict, max_chars=max_json_chars)
    return (
        LinkedSchemaPayload(
            engine=db,
            scoped_names=names,
            linked_schema_json=js,
            readiness_ok=True,
            readiness_message="",
        ),
        "",
    )


def answer_contract_from_planner_json(raw: Dict[str, Any], *, fallback_summary: str = "llm_planner") -> AnswerContract:
    """Normalize LLM planner JSON into :class:`AnswerContract`."""
    grain = str(raw.get("output_grain") or "scalar").strip() or "scalar"

    def _str_list(key: str) -> List[str]:
        v = raw.get(key)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    return AnswerContract(
        summary=str(raw.get("summary") or fallback_summary),
        output_grain=grain,
        metrics=_str_list("metrics"),
        filters=_str_list("filters"),
        dimensions=_str_list("dimensions"),
        time_bounds=_str_list("time_bounds"),
        requires_join_or_group=bool(raw.get("requires_join_or_group", False)),
    )
