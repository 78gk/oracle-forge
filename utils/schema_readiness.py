"""
Hard gate: do not generate SQL/Mongo against tables/collections with missing column/field metadata.

Returns structured codes like ``need_schema_refresh:empty_column_metadata:table`` for upstream handling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


def _table_field_names(database: str, schema_metadata: Dict[str, Any], table: str) -> Optional[Set[str]]:
    """None if table missing from metadata; empty set if present but no fields dict."""
    meta = schema_metadata.get(database) or {}
    tlow = table.strip().lower()
    for item in meta.get("tables") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")).strip().lower() != tlow:
            continue
        fields = item.get("fields") or {}
        if not isinstance(fields, dict):
            return set()
        return {str(k).lower() for k in fields.keys()}
    return None


def _collection_field_names(database: str, schema_metadata: Dict[str, Any], collection: str) -> Optional[Set[str]]:
    meta = schema_metadata.get(database) or {}
    clow = collection.strip().lower()
    for item in meta.get("collections") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")).strip().lower() != clow:
            continue
        fields = item.get("fields") or {}
        if not isinstance(fields, dict):
            return set()
        return {str(k).lower() for k in fields.keys()}
    return None


def schema_gate_sql_tables(
    database: str,
    schema_metadata: Dict[str, Any],
    table_names: List[str],
) -> Tuple[bool, str]:
    """
    Return (True, "") if every named table has non-empty column metadata.
    Otherwise (False, "need_schema_refresh:...") with a stable machine prefix.
    """
    for name in table_names:
        if not name or not str(name).strip():
            continue
        cols = _table_field_names(database, schema_metadata, str(name).strip())
        if cols is None:
            return False, f"need_schema_refresh:missing_table_metadata:{name}"
        if len(cols) == 0:
            return False, f"need_schema_refresh:empty_column_metadata:{name}"
    return True, ""


def schema_gate_mongo_collections(
    database: str,
    schema_metadata: Dict[str, Any],
    collection_names: List[str],
) -> Tuple[bool, str]:
    for name in collection_names:
        if not name or not str(name).strip():
            continue
        fields = _collection_field_names(database, schema_metadata, str(name).strip())
        if fields is None:
            return False, f"need_schema_refresh:missing_collection_metadata:{name}"
        if len(fields) == 0:
            return False, f"need_schema_refresh:empty_collection_fields:{name}"
    return True, ""
