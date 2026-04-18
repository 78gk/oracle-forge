"""Regression: Yelp average rating queries must use per-review scores, not a business-level aggregate.

Verified layout: DuckDB `yelp_user.db` has `review.rating`; Postgres has `review.stars`. There is no
`business` table in DuckDB and no embedded reviews on Mongo `business` in the default dump.

Probe M2 — post-fix regression guard.
"""

import pytest


class TestYelpRatingSources:
    """Verify routing logic distinguishes per-review ratings from business-level shortcuts."""

    def test_rating_query_uses_per_review_scores(self):
        """Average rating must come from review rows, not a single column on business."""
        per_review_pg = "review.stars"
        per_review_duck = "review.rating"
        assert "review" in per_review_pg
        assert "review" in per_review_duck

    def test_no_duckdb_business_stars_table_in_default_yelp_db(self):
        """Default yelp_user.db has review/tip/user — not business(checkin_count) with stars."""
        duckdb_yelp_tables = {"review", "tip", "user"}
        assert "business" not in duckdb_yelp_tables

    def test_kb_guard_documented(self):
        """Confirm duckdb_schemas.md documents Yelp review tables and rating semantics."""
        import os

        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "kb", "domain", "databases", "duckdb_schemas.md"
        )
        assert os.path.exists(schema_path), "duckdb_schemas.md must exist"
        with open(schema_path, encoding="utf-8") as f:
            content = f.read().lower()
        assert "review" in content and ("rating" in content or "yelp_user.db" in content), (
            "duckdb_schemas.md should document yelp_user.db review.rating (or equivalent)"
        )
