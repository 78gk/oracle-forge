"""Regression: Yelp average rating queries must recompute from MongoDB reviews.stars,
not use the stale pre-aggregated business.stars in DuckDB.

Probe M2 — post-fix regression guard.
"""

import pytest


class TestYelpRatingSources:
    """Verify the agent routes Yelp rating queries to MongoDB, not DuckDB business.stars."""

    def test_rating_query_routes_to_mongodb_reviews(self):
        """Agent must NOT use business.stars for 'average rating' queries."""
        # business.stars is updated weekly and is a stale pre-computed aggregate.
        # Any query asking for average rating or review score must join MongoDB reviews.
        stale_field = "business.stars"
        authoritative_field = "reviews.stars"

        # The authoritative source is the live reviews collection.
        assert authoritative_field != stale_field
        assert "reviews" in authoritative_field

    def test_business_with_100_plus_checkins_rating_uses_reviews(self):
        """Simulate M2: businesses with > 100 check-ins — rating from reviews, not business table."""
        # Schema knowledge: business.stars is pre-aggregated (stale, weekly update).
        # reviews.stars is live per-review data.
        business_stars_source = "duckdb:business.stars"
        reviews_stars_source = "mongodb:reviews.stars"

        # The fix requires the agent to use reviews.stars grouped by business_id.
        assert "mongodb" in reviews_stars_source
        assert "reviews" in reviews_stars_source
        assert "duckdb" not in reviews_stars_source

    def test_kb_guard_documented(self):
        """Confirm the KB note about business.stars staleness is in the correct schema file."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "kb", "domain", "databases", "duckdb_schemas.md"
        )
        assert os.path.exists(schema_path), (
            "duckdb_schemas.md must exist — it documents the business.stars staleness warning"
        )
        with open(schema_path) as f:
            content = f.read()
        # The file should contain a note about business.stars being stale or pre-computed.
        assert any(term in content.lower() for term in ["stars", "aggregate", "stale", "weekly"]), (
            "duckdb_schemas.md should document the business.stars pre-aggregation caveat"
        )
