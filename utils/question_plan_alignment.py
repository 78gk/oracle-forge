"""Heuristic checks that generated SQL/pipelines are not trivially misaligned with the question."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def plan_aligns_with_question(
    question: str,
    plan: Dict[str, Any],
    *,
    dataset_playbook: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Return (True, "") when no red flags; otherwise (False, reason_code).

    This does not prove correctness—only catches common “success” plans that ignore the task
    (e.g. ``SELECT * … LIMIT`` for a complex NL question).
    """
    q = (question or "").strip().lower()
    steps: List[Dict[str, Any]] = plan.get("steps") or []
    if not steps or not q:
        return True, ""

    dp = dataset_playbook or {}
    mismatch_terms = [
        str(x).lower().strip()
        for x in (dp.get("avoid_keywords_mismatch") or [])
        if isinstance(x, str) and str(x).strip()
    ]
    mongo_block = (dp.get("engines") or {}).get("mongodb") or {}
    mongo_primary = (
        str(mongo_block.get("primary_collection") or "").strip().lower()
        if isinstance(mongo_block, dict)
        else ""
    )

    for step in steps:
        payload = step.get("query_payload") or {}
        if not isinstance(payload, dict):
            continue
        sql = str(payload.get("sql") or "").strip()
        pipeline = payload.get("pipeline")

        if sql:
            low_sql = sql.lower()
            for term in mismatch_terms:
                if term and term in low_sql:
                    return False, "playbook_forbidden_identifier_in_sql"
            if _is_trivial_select_star_limit(sql):
                if len(q) > 80 or _looks_non_trivial_question(q):
                    return False, "trivial_select_star_limit_for_complex_question"
            if re.search(
                r"(?is)SELECT\s+AVG\s*\(\s*(?:rating|stars)\s*\)(?:\s+AS\s+\w+)?\s+FROM\s+(?:[\w.]+\.)?review\b",
                sql,
            ) and not re.search(r"(?is)\bWHERE\b|\bJOIN\b|\bGROUP\b|\bWITH\b", sql):
                if _question_asks_ranked_region_and_aggregate(q):
                    return False, "avg_rating_only_when_question_requires_state_or_ranking"
                if "indianapolis" in q and "indianapolis" not in low_sql:
                    return False, "missing_location_predicate_for_named_place"
            if ("npm" in q or "package" in q or "github" in q) and "from review" in low_sql:
                return False, "review_table_for_non_yelp_question"

        if isinstance(pipeline, list) and pipeline:
            col = str(payload.get("collection") or "").strip().lower()
            if mongo_primary == "articles" and col == "review" and _looks_news_corpus_question(q):
                return False, "mongo_collection_mismatch_news_question"
            if mismatch_terms:
                pipe_blob = json.dumps(pipeline, ensure_ascii=False).lower()
                for term in mismatch_terms:
                    if term and term in pipe_blob:
                        return False, "playbook_forbidden_identifier_in_pipeline"
            if len(pipeline) == 1 and isinstance(pipeline[0], dict) and "$limit" in pipeline[0]:
                if any(
                    w in q
                    for w in (
                        "greatest",
                        "longest",
                        "top ",
                        "which package",
                        "article whose",
                        "number of characters",
                        "sports article",
                    )
                ):
                    return False, "mongo_pipeline_only_limit_for_aggregation_question"

    return True, ""


def _question_asks_ranked_region_and_aggregate(q: str) -> bool:
    """
    Heuristic: question wants a specific region (state / U.S. / etc.) with superlative volume
    plus a metric — not a single-table global aggregate.
    """
    has_region = any(
        tok in q
        for tok in (
            "state",
            "u.s.",
            "region",
            "province",
            "country",
        )
    )
    has_superlative_or_selection = any(
        tok in q
        for tok in (
            "which ",
            "highest number",
            "most reviews",
            "most review",
            "top ",
            "rank",
            "largest number",
        )
    )
    return bool(has_region and has_superlative_or_selection)


def _looks_news_corpus_question(q: str) -> bool:
    return any(
        w in q
        for w in (
            "article",
            "sports",
            "news",
            "headline",
            "description",
            "longest",
            "title",
        )
    )


def _looks_non_trivial_question(q: str) -> bool:
    return any(
        w in q
        for w in (
            "which ",
            "what ",
            "top ",
            "average",
            "state",
            "npm",
            "github",
            "package",
            "article",
            "title ",
            "greatest",
            "longest",
            "how many",
            "during ",
            "either ",
            "offered ",
            "parking",
            "credit card",
            "distinct ",
            "join ",
            "correlate",
        )
    )


def _is_trivial_select_star_limit(sql: str) -> bool:
    """
    Detect probe-style ``SELECT * FROM … LIMIT n`` (single table, optional schema/AS, no JOIN/WHERE).
    """
    s = sql.strip().rstrip(";")
    if re.search(r"(?is)\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bWITH\b", s):
        return False
    return bool(
        re.match(
            r"(?is)^\s*SELECT\s+\*\s+FROM\s+(?:[\"']?(?:[\w]+\.)?[\w]+[\"']?)(?:\s+AS\s+\w+)?\s+LIMIT\s+\d+\s*$",
            s,
        )
    )

