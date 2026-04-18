"""Phase A: registry vs runtime schema reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.llm_reasoner import OpenRouterRoutingReasoner
from utils.schema_bundle import build_schema_bundle, schema_bundle_json
from utils.schema_registry.reconciliation import reconcile_schema_metadata_with_registry
from utils.schema_registry.routing_compact import compact_registry_routing_summary, load_registry_json_optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_reconcile_replaces_disjoint_mongodb_collections() -> None:
    root = _repo_root()
    reg = load_registry_json_optional(root, "agnews")
    assert reg is not None
    bad_meta = {
        "mongodb": {
            "tables": [],
            "collections": [
                {"name": "business", "fields": {"x": "int"}},
                {"name": "checkin", "fields": {}},
            ],
        }
    }
    out, result = reconcile_schema_metadata_with_registry(
        bad_meta, reg, ["postgresql", "mongodb", "sqlite", "duckdb"]
    )
    assert result["status"] == "repaired"
    names = [c["name"] for c in out["mongodb"]["collections"] if isinstance(c, dict)]
    assert names == ["articles"]
    mongo_blob = json.dumps(out.get("mongodb") or {})
    assert "business" not in mongo_blob
    assert "checkin" not in mongo_blob


def test_reconcile_clears_unavailable_sqlite_when_runtime_has_tables() -> None:
    root = _repo_root()
    reg = load_registry_json_optional(root, "agnews")
    assert reg is not None
    bad_meta = {
        "sqlite": {
            "tables": [{"name": "review", "fields": {}}],
            "collections": [],
        }
    }
    out, result = reconcile_schema_metadata_with_registry(
        bad_meta, reg, ["sqlite", "duckdb", "mongodb"]
    )
    eng = result.get("engines") or {}
    assert eng.get("sqlite", {}).get("action") == "cleared_unavailable_engine"
    assert out["sqlite"]["tables"] == []
    assert out["sqlite"]["collections"] == []


def test_compact_registry_and_bundle_do_not_both_list_yelp_and_articles_for_mongo() -> None:
    """After reconciliation, PRIMARY bundle and compact summary must not disagree on Mongo names."""
    root = _repo_root()
    reg = load_registry_json_optional(root, "agnews")
    assert reg is not None
    bad_meta = {
        "mongodb": {
            "tables": [],
            "collections": [{"name": "business", "fields": {}}],
        }
    }
    out, _ = reconcile_schema_metadata_with_registry(
        bad_meta, reg, ["mongodb", "duckdb", "postgresql", "sqlite"]
    )
    avail = ["mongodb", "duckdb", "postgresql", "sqlite"]
    compact = compact_registry_routing_summary(reg, avail)
    bundle = build_schema_bundle(out, avail, "agnews", playbook=None)
    mongo = bundle["engines"].get("mongodb") or {}
    coll_names = [c.get("name") for c in mongo.get("collections") or [] if isinstance(c, dict)]
    assert coll_names == ["articles"]
    bjson = schema_bundle_json(bundle)
    assert "articles" in bjson
    for line in compact.splitlines():
        if line.strip().startswith("- mongodb:"):
            assert "articles" in line
            assert "business" not in line
            break
    else:
        pytest.fail("expected mongodb line in compact registry summary")


def test_routing_prompt_omits_live_mcp_block_when_registry_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_plan(
        self: OpenRouterRoutingReasoner,
        prompt: str,
        *,
        log_context=None,
    ):
        captured["prompt"] = prompt
        return (
            {
                "selected_databases": ["duckdb"],
                "selected_tables": {"duckdb": ["article_metadata"]},
                "rationale": "test",
                "query_hints": {},
            },
            "{}",
        )

    monkeypatch.setattr(OpenRouterRoutingReasoner, "_plan_with_openrouter", fake_plan)
    root = _repo_root()
    with (root / "artifacts" / "schema_registry" / "agnews.json").open(encoding="utf-8") as fh:
        full_reg = json.load(fh)
    from utils.scoped_schema_pack import schema_metadata_stub_from_registry

    stub_meta = schema_metadata_stub_from_registry(full_reg)
    out, recon = reconcile_schema_metadata_with_registry(
        stub_meta, full_reg, ["duckdb", "mongodb", "postgresql", "sqlite"]
    )
    bundle = build_schema_bundle(out, ["duckdb", "mongodb", "postgresql", "sqlite"], "agnews")
    reasoner = OpenRouterRoutingReasoner(repo_root=root)
    reasoner.openrouter_api_key = "test-key"
    ctx = {
        "user_question": "Count rows",
        "routing_question": "Count rows",
        "dataset_id": "agnews",
        "schema_metadata": out,
        "schema_reconciliation": recon,
        "schema_bundle_json": schema_bundle_json(bundle),
        "context_layers": {},
    }
    reasoner.plan(question="Count rows", available_databases=["duckdb", "mongodb", "postgresql", "sqlite"], context=ctx)
    prompt = captured.get("prompt", "")
    assert "Live MCP schema routing summary" not in prompt
