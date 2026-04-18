"""Tests for DURABLE_FIX_PLAN phases A–C (merge, schema bundle, dataset profiles)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.main import _merge_outputs, _answer_from_metrics
from utils.dataset_profiles import DatasetProfile, load_dataset_profile, pop_profile_env, push_profile_env
from utils.execution_hints import enrich_replan_notes
from utils.schema_bundle import build_schema_bundle, schema_bundle_json


def test_merge_outputs_single_non_empty_second_step():
    trace: list = []
    step_outputs = [
        {"ok": True, "database": "mongodb", "data": []},
        {
            "ok": True,
            "database": "sqlite",
            "data": [{"title": "Sports headline", "text": "x" * 10}],
        },
    ]
    merged = _merge_outputs(step_outputs, trace)
    assert len(merged) == 1
    assert merged[0].get("title") == "Sports headline"
    assert any(e.get("merge_strategy") == "single_non_empty_step" for e in trace)


def test_merge_outputs_join_when_keys_exist():
    trace: list = []
    step_outputs = [
        {"ok": True, "database": "postgresql", "data": [{"id": 1, "name": "a"}]},
        {"ok": True, "database": "mongodb", "data": [{"id": 1, "x": 2}]},
    ]
    _merge_outputs(step_outputs, trace)
    # May join or concat depending on infer_join_key; should not drop all rows silently.
    assert any(e.get("merge_event") or e.get("merge_strategy") for e in trace)


def test_answer_from_metrics_title_column():
    ans = _answer_from_metrics(
        "What is the title of the sports article?",
        {"row_count": 1},
        [{"title": "Hello", "other": 1}],
    )
    assert ans == "Hello"


def test_schema_bundle_has_engines_and_fields():
    meta = {
        "postgresql": {
            "tables": [{"name": "review", "fields": {"stars": "float", "business_id": "text"}}],
            "collections": [],
        }
    }
    b = build_schema_bundle(meta, ["postgresql"], dataset_id="yelp")
    assert b.get("dataset_id") == "yelp"
    pg = b["engines"]["postgresql"]
    assert any(t.get("name") == "review" for t in pg["tables"])
    s = schema_bundle_json(b, max_chars=5000)
    assert "review" in s
    assert json.loads(s)["engines"]["postgresql"]["tables"]


def test_enrich_replan_unknown_table():
    notes = enrich_replan_notes(
        ["Query validation failed: unknown_tables:['foo']"],
        {"postgresql": {"tables": [{"name": "review", "fields": {"x": "int"}}], "collections": []}},
    )
    assert any("schema_constraint" in n for n in notes)


def test_dataset_profile_env_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ORACLE_FORGE_DATASET_TESTDS_SQLITE_PATH", raising=False)
    p = DatasetProfile(dataset_id="testds", sqlite_path=str(tmp_path / "a.db"))
    saved = push_profile_env(p)
    assert "SQLITE_PATH" in __import__("os").environ
    pop_profile_env(p, saved)


def test_load_dataset_profile_missing_returns_none():
    assert load_dataset_profile(None) is None
    assert load_dataset_profile("") is None
