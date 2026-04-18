"""Phase D: routing policy (schema-aware + multi-DB collapse)."""

from __future__ import annotations

from utils.routing_policy import (
    build_schema_routing_summary,
    collapse_multi_db_selection,
    engines_with_nonempty_schema,
    multi_db_warranted,
    normalize_routing_selection,
    score_engine_keyword_overlap,
)


def test_engines_with_nonempty_schema_falls_back_when_all_empty():
    meta = {"postgresql": {"tables": [], "collections": []}}
    avail = ["postgresql", "mongodb"]
    out = engines_with_nonempty_schema(meta, avail)
    assert "postgresql" in out


def test_multi_db_warranted_join():
    assert multi_db_warranted("Compute a join across review and business")
    assert not multi_db_warranted("What is the average rating in Indianapolis")


def test_collapse_to_single_without_cross_db_intent():
    meta = {
        "postgresql": {"tables": [{"name": "review", "fields": {}}], "collections": []},
        "mongodb": {"tables": [], "collections": [{"name": "business", "fields": {}}]},
    }
    sel = collapse_multi_db_selection("Average stars for city X", ["postgresql", "mongodb"], meta)
    assert len(sel) == 1


def test_normalize_prefers_nonempty_and_collapses():
    meta = {
        "postgresql": {"tables": [{"name": "review", "fields": {}}], "collections": []},
        "duckdb": {
            "tables": [{"name": "market_daily", "fields": {}}],
            "collections": [],
        },
    }
    out = normalize_routing_selection(
        "Which stock index has highest volatility since 2020",
        ["postgresql", "duckdb"],
        ["postgresql", "duckdb"],
        meta,
    )
    assert len(out) == 1
    assert out[0] == "duckdb"


def test_schema_routing_summary_lists_tables():
    meta = {"sqlite": {"tables": [{"name": "foo", "fields": {}}], "collections": []}}
    s = build_schema_routing_summary(meta, ["sqlite"])
    assert "foo" in s
    assert "sqlite" in s


def test_score_engine_overlap():
    meta = {"duckdb": {"tables": [{"name": "market_daily", "fields": {}}], "collections": []}}
    assert score_engine_keyword_overlap("stock index volatility", "duckdb", meta) >= 1
