"""
Structured global planning pass (Phase C): question + registry-aligned schema → JSON plan.

Runs after routing and scoped schema bundle build; output is stored on ``context["global_plan"]``
and drives :class:`~agent.query_pipeline.AnswerContract` for query generation when enabled.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import httpx

from agent.utils import canonical_db_name
from utils.llm_io_log import append_llm_io_log
from utils.schema_registry.routing_compact import compact_registry_routing_summary_adaptive, load_registry_json_optional

_logger = logging.getLogger(__name__)


class GlobalPlannerFailed(RuntimeError):
    """OpenRouter global planner failed or returned invalid JSON."""


def global_planner_enabled() -> bool:
    raw = os.getenv("ORACLE_FORGE_GLOBAL_PLANNER")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def global_planner_strict() -> bool:
    return os.getenv("ORACLE_FORGE_GLOBAL_PLANNER_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"your_api_key_here", "your_key_here", "changeme"}:
        return ""
    return value


def _log_global_plan(repo_root: Path, entry: Dict[str, Any]) -> None:
    path = repo_root / "logs" / "global_planner.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.getenv("ORACLE_FORGE_DISABLE_GLOBAL_PLANNER_LOG", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    from datetime import datetime, timezone

    row = dict(entry)
    row.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_global_plan(
    *,
    repo_root: Path,
    question: str,
    routing_question: str,
    context: Dict[str, Any],
    available_databases: List[str],
    http_client: Optional[httpx.Client] = None,
    repair_hints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Single OpenRouter JSON call producing a structured plan (no SQL).

    On failure: raises ``GlobalPlannerFailed`` if strict, else returns ``{"_degraded": True, ...}``.
    """
    load_dotenv(repo_root / ".env", override=False)
    api_key = _clean_env("OPENROUTER_API_KEY")
    if not api_key:
        if global_planner_strict():
            raise GlobalPlannerFailed("OPENROUTER_API_KEY missing for global planner.")
        return {"_degraded": True, "_reason": "no_openrouter_api_key"}

    model = os.getenv("MODEL_NAME", "").strip() or "openai/gpt-4o-mini"
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
    site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
    app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()

    ds = context.get("dataset_id")
    dataset_id = str(ds).strip() if isinstance(ds, str) and str(ds).strip() else ""
    registry = load_registry_json_optional(repo_root, dataset_id) if dataset_id else None
    compact = (
        compact_registry_routing_summary_adaptive(registry, available_databases, repo_root=repo_root)
        if registry
        else ""
    )
    bundle_snip = str(context.get("schema_bundle_json") or "")[:8000]
    llm_g = context.get("llm_guidance") if isinstance(context.get("llm_guidance"), dict) else {}
    sel_db = llm_g.get("selected_databases") if isinstance(llm_g.get("selected_databases"), list) else []
    sel_tbl = llm_g.get("selected_tables") if isinstance(llm_g.get("selected_tables"), dict) else {}
    dp = context.get("dataset_playbook") if isinstance(context.get("dataset_playbook"), dict) else {}
    playbook_snip = str(dp.get("summary", ""))[:2500] if dp else ""

    system = (
        "You are a global analytical planner for a multi-database benchmark agent. "
        "Given the question and ONLY the schema identifiers below, output strict JSON (no SQL, no markdown). "
        "Top-level keys: "
        "selected_databases (array), "
        "selected_tables (object engine→table/collection name arrays), "
        "candidate_join_paths (array of {left_table, right_table, join_condition}), "
        "target_entity (string), "
        "measures (array of strings), "
        "filters (array of strings), "
        "group_by (array of strings), "
        "ranking (null or {order, metric, k}), "
        "time_constraints (array of strings), "
        "output_contract (object — drives query generation; be explicit), "
        "confidence (0-1), "
        "notes (string). "
        "Inside output_contract include: "
        "grain and result_shape each one of scalar | one_row | multi_row | grouped | top_k; "
        "metrics, filters, dimensions (arrays); "
        "requires_join, requires_aggregation, requires_ranking (booleans); "
        "top_k (integer or null). "
        "If the question needs filter + group + aggregate + sort (e.g. highest average X in region Y since Z), "
        "use grain grouped, fill group_by/filters/time_constraints/measures, set requires_aggregation true — "
        "never collapse that into a bare scalar average without dimensions. "
        "selected_tables must use EXACT names from the schema bundle / COMPACT REGISTRY block. "
        "Prefer the smallest engine set that can answer the question."
    )
    if (dataset_id or "").strip().lower() == "yelp":
        system += (
            " For Yelp PostgreSQL, any join_path between review and business must NOT claim bare "
            "business.business_id = review.business_id; the seed uses mismatched id prefixes — describe "
            "join_condition using REPLACE(business_id, 'businessid_', 'businessref_') aligned to review.business_id "
            "(see agent/dab_yelp_postgres.py). Filters for city/state must use real columns in SCHEMA "
            "(e.g. description ILIKE, state_code), not invented business.city unless listed."
        )
    user = (
        f"dataset_id: {dataset_id or '(none)'}\n"
        f"routing_question:\n{routing_question[:6000]}\n\n"
        f"user_question:\n{question[:6000]}\n\n"
        f"routing_llm_selected_databases: {json.dumps(sel_db, ensure_ascii=False)}\n"
        f"routing_llm_selected_tables: {json.dumps(sel_tbl, ensure_ascii=False)}\n\n"
        f"COMPACT_REGISTRY:\n{compact}\n\n"
        f"PRIMARY_SCHEMA_BUNDLE_JSON:\n{bundle_snip}\n\n"
        f"PLAYBOOK_SUMMARY:\n{playbook_snip}\n"
    )
    if repair_hints:
        rh = "\n".join(str(h)[:800] for h in repair_hints[-20:] if str(h).strip())
        if rh.strip():
            user += "\nPRIOR_FAILURE_HINTS (semantic repair — revise plan/contract accordingly):\n" + rh + "\n"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    t0 = time.perf_counter()
    append_llm_io_log(
        repo_root,
        {
            "phase": "global_plan",
            "provider": "openrouter",
            "model": model,
            "messages": body["messages"],
            "dataset_id": dataset_id or None,
            "question_preview": (question or "")[:4000],
        },
    )
    client = http_client or httpx.Client(timeout=55)
    own_client = http_client is None
    parsed: Optional[Dict[str, Any]] = None
    try:
        resp = client.post(f"{base_url}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise GlobalPlannerFailed("OpenRouter returned no choices for global plan.")
        content = choices[0].get("message", {}).get("content", "{}")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        raw = str(content).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not parsed:
            raise GlobalPlannerFailed("Global planner returned empty or non-object JSON.")
    except GlobalPlannerFailed:
        raise
    except Exception as exc:
        if global_planner_strict():
            raise GlobalPlannerFailed(str(exc)) from exc
        _logger.warning("Global planner failed (non-strict): %s", exc)
        return {"_degraded": True, "_reason": str(exc)}
    finally:
        if own_client:
            client.close()

    if parsed is None:
        return {"_degraded": True, "_reason": "empty_parse"}

    from agent.query_pipeline import normalize_global_plan_payload

    parsed = normalize_global_plan_payload(parsed)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    # Normalize selected_databases to canonical names
    sd = parsed.get("selected_databases")
    if isinstance(sd, list):
        parsed["selected_databases"] = [
            canonical_db_name(str(x)) for x in sd if canonical_db_name(str(x))
        ]
    _log_global_plan(
        repo_root,
        {
            "phase": "global_plan",
            "status": "ok",
            "dataset_id": dataset_id or None,
            "duration_ms": duration_ms,
            "model": model,
            "confidence": parsed.get("confidence"),
            "notes_preview": str(parsed.get("notes", ""))[:500],
        },
    )
    return parsed
