"""Default engine order from dataset playbooks (chat CLI)."""

from __future__ import annotations

from pathlib import Path

from utils.dataset_playbooks import default_engines_order_for_dataset


def test_default_engines_no_dataset_is_four_standard() -> None:
    repo = Path(__file__).resolve().parents[1]
    assert default_engines_order_for_dataset(None, repo_root=repo) == [
        "postgresql",
        "mongodb",
        "sqlite",
        "duckdb",
    ]


def test_yelp_playbook_order_includes_expected_engines() -> None:
    repo = Path(__file__).resolve().parents[1]
    order = default_engines_order_for_dataset("yelp", repo_root=repo)
    assert "postgresql" in order
    assert "duckdb" in order
