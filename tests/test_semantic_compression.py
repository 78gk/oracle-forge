"""Phase D: deterministic registry semantic compression."""

from __future__ import annotations

import json
from pathlib import Path

from utils.schema_registry.routing_compact import (
    compact_registry_routing_summary,
    compact_registry_routing_summary_adaptive,
    load_registry_json_optional,
)
from utils.schema_registry.semantic_compression import should_compress_registry


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_should_compress_stockmarket_registry() -> None:
    reg = load_registry_json_optional(_root(), "stockmarket")
    assert reg is not None
    assert should_compress_registry(reg, ["sqlite", "duckdb", "postgresql", "mongodb"])


def test_adaptive_summary_clusters_ticker_tables_for_stockmarket() -> None:
    reg = load_registry_json_optional(_root(), "stockmarket")
    assert reg is not None
    avail = ["sqlite", "duckdb", "postgresql", "mongodb"]
    adaptive = compact_registry_routing_summary_adaptive(reg, avail, repo_root=_root())
    assert "SEMANTIC_SCHEMA_SUMMARY" in adaptive
    assert "per_ticker_ohlc" in adaptive
    assert "2753 tables" in adaptive or "tables — one table per ticker" in adaptive
    assert "FULL_REGISTRY_FILE" in adaptive


def test_small_registry_uses_flat_summary() -> None:
    reg = load_registry_json_optional(_root(), "stockindex")
    assert reg is not None
    avail = ["sqlite", "duckdb"]
    flat = compact_registry_routing_summary(reg, avail)
    adaptive = compact_registry_routing_summary_adaptive(reg, avail, repo_root=_root())
    assert adaptive == flat


def test_answer_contract_from_global_plan_preserves_grouping() -> None:
    from agent.query_pipeline import answer_contract_from_global_plan

    gp = {
        "measures": ["average rating"],
        "filters": ["state = IN", "city = Indianapolis"],
        "group_by": ["business_category.category"],
        "output_contract": {
            "grain": "grouped",
            "metrics": ["avg(stars)"],
            "filters": [],
            "dimensions": ["category"],
            "requires_join": True,
            "requires_aggregation": True,
            "requires_ranking": False,
        },
        "notes": "grouped aggregate",
    }
    c = answer_contract_from_global_plan(gp)
    assert c.output_grain == "per_group"
    assert c.requires_aggregation is True
    assert c.requires_join_or_group is True
    assert c.result_shape == "per_group"
    assert c.dimensions
