"""
Select a small set of tables/collections per engine for scoped SQL-builder prompts (Option B).

Keeps per-LLM-call context small: only relevant physical tables for the question.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set

from utils.dataset_playbooks import playbook_engine_table_preferences


def _canonical_engine(name: str) -> str:
    text = (name or "").strip().lower()
    if "post" in text:
        return "postgresql"
    if "mongo" in text:
        return "mongodb"
    if "duck" in text:
        return "duckdb"
    if "sqlite" in text:
        return "sqlite"
    return text


def _table_names_from_metadata(meta: Dict[str, Any], key: str) -> List[str]:
    out: List[str] = []
    for item in meta.get(key) or []:
        if isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]).strip())
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def list_sql_tables_for_engine(schema_metadata: Dict[str, Any], engine: str) -> List[str]:
    eng = _canonical_engine(engine)
    meta = schema_metadata.get(eng) or {}
    return _table_names_from_metadata(meta, "tables")


def list_collections_for_engine(schema_metadata: Dict[str, Any], engine: str) -> List[str]:
    eng = _canonical_engine(engine)
    meta = schema_metadata.get(eng) or {}
    return _table_names_from_metadata(meta, "collections")


def _apply_avoid_rules(
    question_lower: str, candidates: List[str], playbook: Dict[str, Any], engine: str
) -> List[str]:
    prefs = playbook_engine_table_preferences(playbook, engine)
    out = list(candidates)
    for rule in prefs.get("avoid") or []:
        if not isinstance(rule, dict):
            continue
        kws = [str(k).lower() for k in (rule.get("question_keywords") or []) if k]
        if not kws or not any(k in question_lower for k in kws):
            continue
        avoid = {str(a).lower() for a in (rule.get("avoid") or []) if a}
        if not avoid:
            continue
        out = [c for c in out if c.lower() not in avoid]
    return out if out else candidates


def _score_table_relevance(question_lower: str, table_name: str) -> float:
    """Heuristic score: question overlap with table name tokens + light synonyms."""
    toks = set(re.findall(r"[a-z0-9]+", question_lower))
    t = table_name.lower()
    parts = re.split(r"[_\s]+", t)
    score = 0.0
    for p in parts:
        if len(p) < 2:
            continue
        if p in toks:
            score += 2.0
        if p in question_lower and len(p) > 3:
            score += 1.0
    # Common join / domain hints (Yelp-style)
    syn: List[tuple[Set[str], str]] = [
        ({"review", "rating", "star", "reviewed"}, "review"),
        ({"business", "store", "merchant", "parking", "located", "location", "credit", "card"}, "business"),
        ({"category", "categories", "restaurant", "food"}, "business_category"),
        ({"user", "elite", "yelper"}, "user"),
        ({"tip", "tips"}, "tip"),
    ]
    for keys, needle in syn:
        if needle in t and keys & toks:
            score += 3.0
    if "business_category" in t and ("category" in toks or "categor" in question_lower):
        score += 4.0
    return score


def select_tables_for_sql_engine(
    question: str,
    engine: str,
    schema_metadata: Dict[str, Any],
    playbook: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Return ordered table names for this engine to include in the scoped SQL prompt.
    Uses playbook priority, avoid rules, and keyword overlap. Caps list length.
    """
    eng = _canonical_engine(engine)
    all_tables = list_sql_tables_for_engine(schema_metadata, eng)
    if not all_tables:
        return []

    pb = playbook or {}
    prefs = playbook_engine_table_preferences(pb, eng)
    preferred: List[str] = [str(x) for x in prefs.get("preferred_order") or [] if x]
    max_n = max(1, int(os.getenv("ORACLE_FORGE_SCOPED_TABLES_MAX", "8")))

    q = (question or "").strip().lower()
    candidates = _apply_avoid_rules(q, all_tables, pb, eng)

    scores = {t: _score_table_relevance(q, t) for t in candidates}
    ranked = sorted(candidates, key=lambda t: (-scores[t], t.lower()))

    # Prefer playbook order for ties / when scores are zero
    picked: List[str] = []
    seen: Set[str] = set()
    for name in preferred:
        if name in candidates and name not in seen:
            picked.append(name)
            seen.add(name)
    for t in ranked:
        if t not in seen:
            picked.append(t)
            seen.add(t)

    # If question implies joins, keep more tables; else trim low scores
    boost_join = any(
        w in q for w in (" join ", "correlate", "both ", " and ", " with ", " during ")
    ) or ("average" in q and "state" in q)

    if not boost_join and picked:
        # Single-table bias: take top scoring first, then fill from playbook
        high = [t for t in picked if scores.get(t, 0) >= 2.0]
        if high:
            picked = high[:max_n]
        else:
            picked = picked[: min(3, max_n)]

    out = picked[:max_n]
    if not out:
        out = all_tables[: min(max_n, len(all_tables))]
    return out


def select_collections_for_mongo_engine(
    question: str,
    schema_metadata: Dict[str, Any],
    playbook: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """One or few collection names for MongoDB scoped prompt."""
    all_c = list_collections_for_engine(schema_metadata, "mongodb")
    if not all_c:
        return []
    pb = playbook or {}
    primary = None
    m = (pb.get("engines") or {}).get("mongodb") or {}
    if isinstance(m, dict) and m.get("primary_collection"):
        primary = str(m["primary_collection"]).strip()
    max_n = max(1, int(os.getenv("ORACLE_FORGE_SCOPED_COLLECTIONS_MAX", "3")))
    q = (question or "").lower()
    scored = sorted(
        all_c,
        key=lambda c: (-_score_table_relevance(q, c), c.lower()),
    )
    out: List[str] = []
    if primary and primary in all_c:
        out.append(primary)
    for c in scored:
        if c not in out:
            out.append(c)
        if len(out) >= max_n:
            break
    return out[:max_n] if out else all_c[:max_n]


def build_scoped_engine_schema_dict(
    schema_metadata: Dict[str, Any],
    engine: str,
    table_names: Optional[List[str]] = None,
    collection_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Subset of schema_metadata for one engine: only listed tables/collections with fields.
    """
    eng = _canonical_engine(engine)
    meta = schema_metadata.get(eng) or {}
    out: Dict[str, Any] = {"engine": eng, "tables": [], "collections": []}
    want_t = {t.lower() for t in (table_names or []) if t}
    want_c = {c.lower() for c in (collection_names or []) if c}

    for item in meta.get("tables") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"]).strip()
        if want_t and name.lower() not in want_t:
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        out["tables"].append(
            {
                "name": name,
                "columns": sorted(fields.keys())[:240] if fields else [],
            }
        )

    for item in meta.get("collections") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"]).strip()
        if want_c and name.lower() not in want_c:
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        out["collections"].append(
            {
                "name": name,
                "sample_field_keys": sorted(fields.keys())[:120] if fields else [],
            }
        )
    return out
