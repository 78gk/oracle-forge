from __future__ import annotations

from pathlib import Path

from eval.evaluator import OracleForgeEvaluator


def test_list_dataagentbench_dataset_keys_includes_yelp() -> None:
    ev = OracleForgeEvaluator(repo_root=Path(__file__).resolve().parents[2])
    keys = ev.list_dataagentbench_dataset_keys()
    assert "yelp" in keys
    assert len(keys) >= 1


def test_load_multi_two_per_dataset() -> None:
    ev = OracleForgeEvaluator(repo_root=Path(__file__).resolve().parents[2])
    rows = ev.load_dataagentbench_queries_multi(
        per_dataset=2,
        datasets=["yelp", "agnews"],
    )
    assert len(rows) <= 4
    by_ds: dict[str, int] = {}
    for r in rows:
        assert "dataset" in r
        by_ds[r["dataset"]] = by_ds.get(r["dataset"], 0) + 1
    assert by_ds.get("yelp", 0) <= 2
    assert by_ds.get("agnews", 0) <= 2
