"""Replan note enrichment for Postgres tool errors."""

from __future__ import annotations

from utils.execution_hints import enrich_replan_notes, _postgres_table_column_cheat_sheet


def test_cheat_sheet_lists_tables() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business_category", "fields": {"business_id": "text", "category": "text"}},
                {"name": "review", "fields": {"date": "text", "stars": "integer"}},
            ]
        }
    }
    s = _postgres_table_column_cheat_sheet(meta)
    assert "business_category" in s
    assert "category" in s


def test_enrich_adds_inventory_when_alias_column_error() -> None:
    err = "ERROR: column bc.category_name does not exist (SQLSTATE 42703)"
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business_category", "fields": {"business_id": "text", "category": "text"}},
            ]
        }
    }
    out = enrich_replan_notes([err], meta)
    assert any("postgresql_inventory" in x or "inventory" in x for x in out)
    assert any("business_category" in x for x in out)
