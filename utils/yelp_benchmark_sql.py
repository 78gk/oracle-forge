"""
Deterministic SQL fragments aligned with ``scripts/reconcile_yelp_ground_truth.py`` parking logic.

Do not use free-form English phrase matching on ``business.attributes`` for benchmark parity.
"""

from __future__ import annotations

# Matches reconcile q3: BikeParking literal + BusinessParking nested True for garage|street|validated|lot|valet


def yelp_attributes_parking_offer_sql(expr: str = "b.attributes") -> str:
    """
    Boolean SQL expression (PostgreSQL) true when Yelp-style attributes indicate bike or business parking.

    ``expr`` should be the attributes column or cast text (e.g. ``b.attributes``).
    """
    e = expr.strip() if expr.strip() else "b.attributes"
    # str(attributes) contains Python-dict-like substrings; same semantics as reconcile_yelp_ground_truth.q3
    bike = f"({e}::text LIKE '%''BikeParking'': ''True''%')"
    biz = (
        f"({e}::text ~ 'BusinessParking.*(garage|street|validated|lot|valet).*: True')"
    )
    return f"({bike} OR {biz})"


def yelp_parking_question_hint_line() -> str:
    """One line for prompts / playbook references (no executable SQL)."""
    return (
        "Yelp parking (deterministic): use yelp_attributes_parking_offer_sql(b.attributes) — "
        "not ILIKE English phrases like '%bike parking%'."
    )
