"""Table scoping for per-database SQL builder."""

from __future__ import annotations

from utils.sql_builder_scope import build_scoped_engine_schema_dict, select_tables_for_sql_engine


def test_build_scoped_engine_schema_dict_filters_tables() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "review", "fields": {"stars": "int", "business_id": "text"}},
                {"name": "business", "fields": {"business_id": "text", "state_code": "text"}},
            ]
        }
    }
    scoped = build_scoped_engine_schema_dict(meta, "postgresql", table_names=["review"])
    assert len(scoped["tables"]) == 1
    assert scoped["tables"][0]["name"] == "review"
    assert "stars" in scoped["tables"][0]["columns"]


def test_select_tables_prefers_review_for_rating_question() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business", "fields": {"business_id": "text"}},
                {"name": "review", "fields": {"stars": "int"}},
            ]
        }
    }
    tables = select_tables_for_sql_engine(
        "What is the average rating in Indianapolis?",
        "postgresql",
        meta,
        playbook={},
    )
    assert "review" in tables
