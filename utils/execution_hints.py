"""Structured replan hints from tool errors (DURABLE_FIX_PLAN Phase B)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from utils.repair_packet import RepairPacket


_PG_MISSING_COL = re.compile(r'column\s+"([^"]+)"\s+does not exist', re.IGNORECASE)
_PG_MISSING_COL_QUAL = re.compile(r"column\s+([a-z0-9_]+)\.([a-z0-9_]+)\s+does not exist", re.IGNORECASE)
_UNKNOWN_TABLE = re.compile(r"unknown_tables:\s*\[([^\]]*)\]", re.IGNORECASE)


def _postgres_table_column_cheat_sheet(schema_metadata: Dict[str, Any], *, max_tables: int = 16) -> str:
    """Compact `table: col1, col2, ...` for replan hints (aliases are not table names — match physical tables)."""
    db = schema_metadata.get("postgresql") or {}
    parts: List[str] = []
    for item in (db.get("tables") or [])[:max_tables]:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"]).strip()
        fields = item.get("fields") or {}
        if not isinstance(fields, dict) or not fields:
            parts.append(f"{name}: (columns not loaded — refresh schema introspection)")
            continue
        cols = ", ".join(list(fields.keys())[:45])
        parts.append(f"{name}: {cols}")
    return " | ".join(parts) if parts else "(no postgresql.tables in schema_metadata)"


def _field_candidates_for_table(schema_metadata: Dict[str, Any], engine: str, table: str) -> List[str]:
    db = schema_metadata.get(engine) or {}
    for key in ("tables", "collections"):
        for item in db.get(key) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).lower() != table.lower():
                continue
            fields = item.get("fields") or {}
            if isinstance(fields, dict):
                return list(fields.keys())[:80]
    return []


def enrich_replan_notes(
    step_errors: List[str],
    schema_metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Append concrete hints so the query generator can change behavior on retry."""
    schema_metadata = schema_metadata or {}
    extra: List[str] = []
    for raw in step_errors:
        text = str(raw)
        before = len(extra)
        m = _UNKNOWN_TABLE.search(text)
        if m:
            extra.append(
                "schema_constraint: Replace unknown table(s) with names from schema_bundle engines.*.tables "
                f"or collections; invalid reference: {m.group(0)}"
            )
        for rx in (_PG_MISSING_COL_QUAL, _PG_MISSING_COL):
            for m in rx.finditer(text):
                if m.lastindex and m.lastindex >= 2:
                    tbl = m.group(1)
                    col = m.group(2)
                    candidates = _field_candidates_for_table(schema_metadata, "postgresql", tbl)
                    if candidates:
                        extra.append(
                            f"schema_constraint: PostgreSQL table `{tbl}` has no column `{col}`. "
                            f"Use only these fields for `{tbl}`: {candidates[:25]}"
                        )
                    else:
                        cheat = _postgres_table_column_cheat_sheet(schema_metadata)
                        extra.append(
                            f"schema_constraint: `{tbl}.{col}` is invalid — `{tbl}` may be an ALIAS, not a table name. "
                            f"Use exact column names from the physical table (see inventory). "
                            f"postgresql_inventory: {cheat}"
                        )
                elif m.lastindex:
                    col = m.group(1)
                    extra.append(
                        f"schema_constraint: Column `{col}` invalid for this schema — "
                        "join review/business tables per schema_bundle fields; do not assume columns on business alone."
                    )
        if "unknown_columns" in text or "unknown_column" in text.lower():
            extra.append(
                "schema_constraint: Validation failed — use only columns listed under engines.<db>.tables[].fields "
                "for that step's database; do not reuse column names from another engine."
            )
        if "does not exist" in text.lower() and "column" in text.lower() and len(extra) == before:
            cheat = _postgres_table_column_cheat_sheet(schema_metadata)
            extra.append(
                "schema_constraint: Regenerate SQL using only table and column names from schema metadata. "
                f"Do not invent names (e.g. category_name vs category). postgresql_inventory: {cheat}"
            )
        if re.search(r"operator\s+does\s+not\s+exist.*text.*date", text, re.IGNORECASE | re.DOTALL) or (
            "42883" in text and "date" in text.lower() and "text" in text.lower()
        ):
            extra.append(
                "dialect_fix: PostgreSQL cannot compare TEXT/VARCHAR date columns to DATE literals directly. "
                "Use CAST(column AS date), column::date, or to_date(column, ...) on the text column before comparing "
                "to DATE '...' (check schema column types for review.date and similar)."
            )
    out = list(step_errors)
    for line in extra:
        if line and line not in out:
            out.append(line)
    struct_tail: List[str] = []
    for raw in step_errors:
        t = str(raw)
        if "unknown_tables:" in t:
            struct_tail.append(
                RepairPacket(error_type="unknown_table", hint=t[:800], ctes_allowed=True).to_prompt_line()
            )
        if "unknown_columns" in t:
            struct_tail.append(
                RepairPacket(error_type="unknown_column", hint=t[:800], ctes_allowed=True).to_prompt_line()
            )
    for p in struct_tail:
        if p and p not in out:
            out.append(p)
    return out[:36]
