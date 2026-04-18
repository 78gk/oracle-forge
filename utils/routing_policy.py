"""Phase D: schema-aware routing constraints and multi-database policy (DURABLE_FIX_PLAN §3)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from agent.utils import canonical_db_name


def _table_coll_names(meta: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for key in ("tables", "collections"):
        for item in meta.get(key) or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
    return names


def engines_with_nonempty_schema(schema_metadata: Dict[str, Any], available: List[str]) -> List[str]:
    """
    Engines that have at least one table or collection in introspection.
    If none have metadata (cold MCP), returns `available` unchanged so routing still runs.
    """
    out: List[str] = []
    for raw in available:
        db = canonical_db_name(str(raw))
        if not db:
            continue
        meta = schema_metadata.get(db) if isinstance(schema_metadata, dict) else {}
        if not isinstance(meta, dict):
            continue
        tables = meta.get("tables") or []
        cols = meta.get("collections") or []
        if (isinstance(tables, list) and len(tables) > 0) or (isinstance(cols, list) and len(cols) > 0):
            out.append(db)
    return out if out else [canonical_db_name(x) for x in available if canonical_db_name(str(x))]


def build_schema_routing_summary(schema_metadata: Dict[str, Any], available: List[str], max_tables: int = 12) -> str:
    """Compact line-per-engine summary for the routing LLM (table/collection names only)."""
    if not isinstance(schema_metadata, dict):
        return ""
    lines: List[str] = []
    for raw in available:
        db = canonical_db_name(str(raw))
        if not db:
            continue
        meta = schema_metadata.get(db) or {}
        if not isinstance(meta, dict):
            continue
        tnames = _table_coll_names(meta)[:max_tables]
        if not tnames:
            continue
        lines.append(f"- {db}: {', '.join(tnames)}")
    return "\n".join(lines) if lines else "(no table/collection names in introspection)"


def multi_db_warranted(question: str) -> bool:
    """True when the question plausibly requires more than one engine (join / cross-store)."""
    q = (question or "").lower()
    if any(
        tok in q
        for tok in (
            " join ",
            "join ",
            " correlate",
            "across databases",
            "across both",
            "combine ",
            "relational and document",
            "sql and mongo",
            "postgres and mongo",
            "postgresql and mongo",
        )
    ):
        return True
    if re.search(r"\bacross\b.*\b(and|both)\b", q):
        return True
    if " and " in q and sum(1 for w in ("mongo", "document", "postgres", "sql", "sqlite", "duckdb") if w in q) >= 2:
        return True
    return False


def score_engine_keyword_overlap(question: str, db: str, schema_metadata: Dict[str, Any]) -> int:
    """Rough relevance: schema object names appearing in the question text."""
    q = (question or "").lower()
    meta = schema_metadata.get(db) or {}
    if not isinstance(meta, dict):
        return 0
    score = 0
    for name in _table_coll_names(meta):
        n = name.lower()
        if len(n) >= 3 and n in q:
            score += 2
        elif len(n) >= 4 and any(token in q for token in re.split(r"[_\s]+", n) if len(token) >= 4):
            score += 1
    # Light engine keywords (avoid over-weighting generic tokens)
    if db == "duckdb" and any(
        t in q
        for t in (
            "analytics",
            "aggregate",
            "window",
            "trend",
            "volatility",
            "intraday",
            "stock",
            "index",
            "trading",
            "ohlc",
        )
    ):
        score += 2
    if db == "sqlite" and any(t in q for t in ("transaction", "etf", "security", "listing")):
        score += 1
    if db == "mongodb" and any(t in q for t in ("document", "nested", "pipeline", "aggregation", "article", "text")):
        score += 1
    if db == "postgresql" and any(t in q for t in ("relational", "subscriber", "join", "sql")):
        score += 1
    return score


def collapse_multi_db_selection(
    question: str,
    selected: List[str],
    schema_metadata: Dict[str, Any],
) -> List[str]:
    """
    If multiple engines were chosen but the question does not warrant cross-DB work,
    keep a single best-scoring engine (schema name overlap + light keywords).
    """
    norm = [canonical_db_name(x) for x in selected if canonical_db_name(str(x))]
    if len(norm) <= 1:
        return norm
    if multi_db_warranted(question):
        return norm
    scores = [(score_engine_keyword_overlap(question, db, schema_metadata), i, db) for i, db in enumerate(norm)]
    scores.sort(key=lambda x: (-x[0], x[1]))
    best = scores[0][2]
    return [best]


def normalize_routing_selection(
    question: str,
    selected: List[str],
    available: List[str],
    schema_metadata: Dict[str, Any],
) -> List[str]:
    """Filter to available + nonempty schema engines, then optionally collapse multi-DB."""
    avail = [canonical_db_name(x) for x in available if canonical_db_name(str(x))]
    seen: Set[str] = set()
    norm: List[str] = []
    for db in selected:
        c = canonical_db_name(str(db))
        if c in avail and c not in seen:
            seen.add(c)
            norm.append(c)
    nonempty = engines_with_nonempty_schema(schema_metadata, avail)
    filtered = [db for db in norm if db in nonempty]
    if not filtered:
        filtered = nonempty[:]
    if not filtered:
        filtered = norm[:]
    collapsed = collapse_multi_db_selection(question, filtered, schema_metadata)
    return collapsed if collapsed else filtered


def first_instruction_line(routing_question: str, question: str) -> str:
    """First non-empty line (benchmark task line) for routing context."""
    text = (routing_question or question or "").strip()
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s[:400]
    return ""
