"""Deterministic Yelp helpers + semantic contract for parking-style questions."""

from __future__ import annotations

from agent.query_pipeline import build_answer_contract
from utils.yelp_benchmark_sql import yelp_attributes_parking_offer_sql


def test_parking_predicate_matches_reconcile_semantics() -> None:
    """No ILIKE English phrases; uses BikeParking literal + BusinessParking regex."""
    pred = yelp_attributes_parking_offer_sql("b.attributes")
    assert "ILIKE" not in pred.upper()
    assert "BikeParking" in pred
    assert "BusinessParking" in pred


def test_parking_question_contract_flags_filters_and_time() -> None:
    q = "During 2018, how many businesses that received reviews offered either business parking or bike parking?"
    c = build_answer_contract(q, "yelp")
    assert "parking_offer" in c.filters
    assert c.time_bounds


def test_contract_is_not_empty_for_yelp_parking() -> None:
    q = "During 2018, how many businesses that received reviews offered either business parking or bike parking?"
    c = build_answer_contract(q, "yelp")
    assert "count" in c.metrics
