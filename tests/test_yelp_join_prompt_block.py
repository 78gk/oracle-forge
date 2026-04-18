"""Yelp Postgres join prompt fragment for LLM SQL generation."""

from __future__ import annotations

from utils.yelp_benchmark_sql import yelp_postgres_review_business_join_prompt_block


def test_join_prompt_mentions_replace_and_forbids_naive_equality() -> None:
    s = yelp_postgres_review_business_join_prompt_block()
    assert "REPLACE" in s and "businessid_" in s and "businessref_" in s
    assert "r.business_id = b.business_id" in s
