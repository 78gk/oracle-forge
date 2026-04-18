"""Load per-benchmark dataset playbooks (table/collection intent for routing and query generation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _canonical_engine(name: str) -> str:
    """Match agent routing names (postgresql, mongodb, duckdb, sqlite)."""
    t = (name or "").strip().lower()
    if "post" in t:
        return "postgresql"
    if "mongo" in t:
        return "mongodb"
    if "duck" in t:
        return "duckdb"
    if "sqlite" in t:
        return "sqlite"
    return t


def load_dataset_playbook(dataset_id: Optional[str], repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Return playbook dict for ``dataset_id``, or empty dict."""
    if not dataset_id or not str(dataset_id).strip():
        return {}
    rid = str(dataset_id).strip()
    root = repo_root or Path(__file__).resolve().parents[1]
    path = root / "kb" / "domain" / "dataset_playbooks.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    datasets = data.get("datasets") or {}
    return datasets.get(rid) or datasets.get(rid.lower()) or {}


def playbook_routing_hint(playbook: Dict[str, Any]) -> str:
    """Short text for LLM routing / query prompts."""
    if not playbook:
        return ""
    parts = [playbook.get("summary", "").strip()]
    eng = playbook.get("engines") or {}
    for db, block in eng.items():
        if not isinstance(block, dict):
            continue
        role = (block.get("role") or "").strip()
        if role:
            parts.append(f"{db}: {role}")
    return "\n".join(p for p in parts if p).strip()


def playbook_engine_table_preferences(playbook: Dict[str, Any], engine: str) -> Dict[str, Any]:
    """Per-engine ``table_priority`` and ``avoid_tables_when`` (postgresql, sqlite, duckdb, …)."""
    if not playbook or not (engine or "").strip():
        return {"preferred_order": [], "avoid": []}
    eng = (playbook.get("engines") or {}).get(engine.strip()) or {}
    if not isinstance(eng, dict):
        return {"preferred_order": [], "avoid": []}
    return {
        "preferred_order": list(eng.get("table_priority") or []),
        "avoid": list(eng.get("avoid_tables_when") or []),
    }


def playbook_sqlite_preferences(playbook: Dict[str, Any]) -> Dict[str, Any]:
    """SQLite table ranking and avoid rules from playbook."""
    return playbook_engine_table_preferences(playbook, "sqlite")


def playbook_mongo_primary_collection(playbook: Dict[str, Any]) -> Optional[str]:
    mongodb = (playbook.get("engines") or {}).get("mongodb") or {}
    return (mongodb.get("primary_collection") or "").strip() or None


def playbook_engine_generation_hints(playbook: Dict[str, Any], engine: str) -> List[str]:
    """
    Optional declarative hints from ``dataset_playbooks.json`` for a target engine.

    Sources (merged, de-duplicated): ``generation_hints_per_engine.<engine>`` and
    ``engines.<engine>.generation_hints``. Intended for stable semantics (join conventions,
    aggregation shape) without embedding benchmark-specific SQL in Python.
    """
    if not playbook or not (engine or "").strip():
        return []
    canon = _canonical_engine(engine)
    out: List[str] = []
    seen: set[str] = set()

    gmap = playbook.get("generation_hints_per_engine")
    if isinstance(gmap, dict):
        raw = gmap.get(canon) or gmap.get(engine.strip().lower())
        if isinstance(raw, list):
            for item in raw:
                s = str(item).strip() if isinstance(item, str) else ""
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)

    eng_block = (playbook.get("engines") or {}).get(canon)
    if not isinstance(eng_block, dict):
        eng_block = (playbook.get("engines") or {}).get(engine.strip().lower())
    if isinstance(eng_block, dict):
        gh = eng_block.get("generation_hints")
        if isinstance(gh, list):
            for item in gh:
                s = str(item).strip() if isinstance(item, str) else ""
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)

    return out


def playbook_generation_hints_markdown(playbook: Dict[str, Any], engines: List[str]) -> str:
    """Format hints for all ``engines`` that have entries (for monolithic multi-step prompts)."""
    if not playbook or not engines:
        return ""
    lines: List[str] = []
    for raw in engines:
        e = _canonical_engine(str(raw))
        hints = playbook_engine_generation_hints(playbook, e)
        if not hints:
            continue
        lines.append(f"[{e}]")
        lines.extend(f"- {h}" for h in hints)
    return "\n".join(lines).strip()
