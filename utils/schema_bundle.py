"""Compact schema bundle for LLM identifier grounding (DURABLE_FIX_PLAN Phase B)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _canonical_db_name(name: str) -> str:
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


def _object_names_and_fields(items: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, str):
            out.append({"name": item, "fields": []})
        elif isinstance(item, dict):
            name = item.get("name", "unknown")
            fields = item.get("fields", {})
            field_keys: List[str] = []
            if isinstance(fields, dict):
                field_keys = list(fields.keys())[:120]
            out.append({"name": str(name), "fields": field_keys})
    return out


def build_schema_bundle(
    schema_metadata: Dict[str, Any],
    selected_databases: List[str],
    dataset_id: Optional[str] = None,
    playbook: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Authoritative structure for query generation: table/collection names + field keys per engine.
    Optional ``playbook`` adds benchmark-level intent (summary, engine roles) for all DBs.
    """
    bundle: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "engines": {},
    }
    for raw in selected_databases:
        db = _canonical_db_name(str(raw))
        if not db:
            continue
        meta = schema_metadata.get(db) or {}
        bundle["engines"][db] = {
            "tables": _object_names_and_fields(meta.get("tables")),
            "collections": _object_names_and_fields(meta.get("collections")),
        }
    if playbook:
        eng = playbook.get("engines") or {}
        roles: Dict[str, str] = {}
        for name, block in eng.items():
            if isinstance(block, dict) and (block.get("role") or "").strip():
                roles[str(name)] = str(block.get("role", "")).strip()[:1200]
        bundle["benchmark_playbook"] = {
            "summary": str(playbook.get("summary", ""))[:8000],
            "engine_roles": roles,
            "suggest_engines_order": list(playbook.get("suggest_engines_order") or [])[:20],
        }
    return bundle


def schema_bundle_json(bundle: Dict[str, Any], max_chars: int = 12000) -> str:
    text = json.dumps(bundle, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def narrow_schema_bundle_json(bundle_json: str, selected_databases: List[str]) -> str:
    """Keep only engines the planner selected so the query generator prompt stays focused."""
    if not bundle_json.strip():
        return bundle_json
    try:
        data = json.loads(bundle_json)
    except Exception:
        return bundle_json
    eng = data.get("engines") or {}
    if not isinstance(eng, dict):
        return bundle_json
    sel = {_canonical_db_name(s) for s in selected_databases if s}
    if not sel:
        return bundle_json
    filtered = {k: v for k, v in eng.items() if _canonical_db_name(k) in sel}
    if not filtered:
        return bundle_json
    out = dict(data)
    out["engines"] = filtered
    for key in ("benchmark_playbook", "dataset_id"):
        if key in data and key not in out:
            out[key] = data[key]
    text = json.dumps(out, ensure_ascii=False)
    max_chars = int(__import__("os").getenv("ORACLE_FORGE_QUERY_GEN_MAX_SCHEMA_CHARS", "14000"))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
