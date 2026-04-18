"""
Reconcile live MCP/schema_metadata with the authoritative schema registry.

When a dataset registry exists, runtime introspection must not inject contradictory
table/collection names into prompts. This module repairs ``schema_metadata`` to match
registry identifiers (names + column keys from the registry), optionally preserving
runtime ``fields`` maps when object names match after reconciliation.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.utils import canonical_db_name
from utils.scoped_schema_pack import schema_metadata_stub_from_registry
from utils.schema_registry.routing_compact import allowed_tables_by_database


def _engine_block_for_db(registry: Dict[str, Any], db: str) -> Optional[Dict[str, Any]]:
    for eng_key, eng in (registry.get("engines") or {}).items():
        if canonical_db_name(str(eng_key)) == db and isinstance(eng, dict):
            return eng
    return None


def _runtime_object_names(meta_db: Dict[str, Any]) -> Tuple[Set[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    tables = meta_db.get("tables") or []
    colls = meta_db.get("collections") or []
    names: Set[str] = set()
    tlist: List[Dict[str, Any]] = [x for x in tables if isinstance(x, dict)]
    clist: List[Dict[str, Any]] = [x for x in colls if isinstance(x, dict)]
    for item in tlist + clist:
        n = item.get("name")
        if n:
            names.add(str(n))
    return names, tlist, clist


def _find_item(items: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and str(item.get("name", "")) == name:
            return item
    return None


def _merge_table_row(
    stub_row: Dict[str, Any],
    runtime_row: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Prefer runtime field types when names align; fall back to registry columns."""
    out = copy.deepcopy(stub_row)
    if not runtime_row:
        return out
    rf = runtime_row.get("fields")
    if isinstance(rf, dict) and rf:
        out["fields"] = {str(k): str(v) for k, v in rf.items()}
    return out


def _merge_collection_row(
    stub_row: Dict[str, Any],
    runtime_row: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    out = copy.deepcopy(stub_row)
    if not runtime_row:
        return out
    rf = runtime_row.get("fields")
    if isinstance(rf, dict) and rf:
        out["fields"] = {str(k): str(v) for k, v in rf.items()}
    return out


def reconcile_schema_metadata_with_registry(
    schema_metadata: Dict[str, Any],
    registry: Dict[str, Any],
    available_databases: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Return a deep-copied, registry-aligned ``schema_metadata`` and a structured result dict.

    Precedence: registry object names and column lists define allowed identifiers; runtime
    may only contribute ``fields`` typing when the object name survives reconciliation.
    """
    if not registry or not isinstance(registry, dict):
        return copy.deepcopy(schema_metadata), {"status": "skipped", "reason": "no_registry"}

    did = str(registry.get("dataset_id") or "").strip()
    stub_all = schema_metadata_stub_from_registry(registry)
    allowed_map = allowed_tables_by_database(registry)
    avail = [canonical_db_name(x) for x in available_databases if canonical_db_name(str(x))]
    seen: List[str] = []
    for d in avail:
        if d not in seen:
            seen.append(d)
    avail = seen

    out_meta = copy.deepcopy(schema_metadata)
    engine_reports: Dict[str, Any] = {}
    repaired = False

    for db in avail:
        block = _engine_block_for_db(registry, db)
        explicit_unavailable = bool(
            isinstance(block, dict) and block.get("available") is False
        )
        allowed = allowed_map.get(db) or set()
        stub_db = stub_all.get(db) if isinstance(stub_all.get(db), dict) else {}
        if not isinstance(stub_db, dict):
            stub_db = {}
        runtime_db = out_meta.get(db)
        if not isinstance(runtime_db, dict):
            runtime_db = {"tables": [], "collections": []}
        runtime_names, rt_tables, rt_colls = _runtime_object_names(runtime_db)

        if explicit_unavailable and runtime_names:
            out_meta[db] = {"tables": [], "collections": []}
            engine_reports[db] = {
                "action": "cleared_unavailable_engine",
                "removed_names": sorted(runtime_names),
            }
            repaired = True
            continue

        if not allowed:
            continue

        if runtime_names and runtime_names.isdisjoint(allowed):
            out_meta[db] = copy.deepcopy(stub_db) if stub_db else {"tables": [], "collections": []}
            engine_reports[db] = {
                "action": "replaced_disjoint_runtime",
                "runtime_had": sorted(runtime_names),
                "registry_allows": sorted(allowed),
            }
            repaired = True
            continue

        # Partial overlap or subset: keep only registry-allowed names; fill from stub.
        stub_tables = stub_db.get("tables") or []
        stub_colls = stub_db.get("collections") or []
        if not isinstance(stub_tables, list):
            stub_tables = []
        if not isinstance(stub_colls, list):
            stub_colls = []

        new_tables: List[Dict[str, Any]] = []
        new_colls: List[Dict[str, Any]] = []
        removed = sorted(runtime_names - allowed)
        for name in sorted(allowed):
            st = _find_item(stub_tables, name)
            cs = _find_item(stub_colls, name)
            rt_t = _find_item(rt_tables, name)
            rt_c = _find_item(rt_colls, name)
            if st is not None:
                new_tables.append(_merge_table_row(st, rt_t))
            elif cs is not None:
                new_colls.append(_merge_collection_row(cs, rt_c))
            # If neither stub row exists, skip (registry / stub inconsistency).

        if removed or (sorted(runtime_names) != sorted(allowed & runtime_names)):
            repaired = True
        out_meta[db] = {"tables": new_tables, "collections": new_colls}
        detail: Dict[str, Any] = {
            "action": "filtered_to_registry",
            "allowed": sorted(allowed),
        }
        if removed:
            detail["removed_names"] = removed
        engine_reports[db] = detail

    # Preserve validation attachment if stub had it
    if "_validation_registry" in stub_all:
        out_meta["_validation_registry"] = copy.deepcopy(stub_all["_validation_registry"])

    status = "repaired" if repaired else "ok"
    result: Dict[str, Any] = {
        "status": status,
        "dataset_id": did or None,
        "engines": engine_reports,
        "suppress_live_mcp_routing_summary": True,
        "authoritative_source": "artifacts/schema_registry",
    }
    return out_meta, result
