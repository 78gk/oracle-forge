"""Lightweight unittest-based checks (no pytest required)."""

from __future__ import annotations

import unittest

from eval.evaluator import OracleForgeEvaluator
from utils.dataset_playbooks import load_dataset_playbook, playbook_engine_generation_hints
from utils.question_plan_alignment import plan_aligns_with_question


class TestGroundTruthFuzzy(unittest.TestCase):
    def test_multiset_numeric_close(self) -> None:
        ev = OracleForgeEvaluator()
        self.assertTrue(ev._multiset_equal_fuzzy(["3.54701", "pa"], ["3.547008", "pa"]))

    def test_multiset_permutation(self) -> None:
        ev = OracleForgeEvaluator()
        self.assertTrue(ev._multiset_equal_fuzzy(["1", "2"], ["2", "1"]))


class TestPlanAlignment(unittest.TestCase):
    def test_rejects_bare_avg_for_state_question(self) -> None:
        ok, reason = plan_aligns_with_question(
            "Which U.S. state has the highest number of reviews, and what is the average rating?",
            {"steps": [{"query_payload": {"sql": "SELECT AVG(rating) FROM review"}}]},
        )
        self.assertFalse(ok)
        self.assertIn("state", reason)

    def test_rejects_bare_avg_stars_for_state_question(self) -> None:
        ok, reason = plan_aligns_with_question(
            "Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state?",
            {"steps": [{"query_payload": {"sql": "SELECT AVG(stars) AS avg_rating FROM review"}}]},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "avg_rating_only_when_question_requires_state_or_ranking")

    def test_rejects_trivial_star_with_as_alias_for_complex_question(self) -> None:
        ok, reason = plan_aligns_with_question(
            "During 2018, how many businesses that received reviews offered either business parking or bike parking?",
            {"steps": [{"query_payload": {"sql": "SELECT * FROM public.review AS r LIMIT 100"}}]},
        )
        self.assertFalse(ok)
        self.assertIn("trivial", reason)

    def test_playbook_engine_generation_hints_yelp_postgresql(self) -> None:
        pb = load_dataset_playbook("yelp")
        hints = playbook_engine_generation_hints(pb, "postgresql")
        self.assertTrue(any("GROUP BY" in h for h in hints))
        self.assertTrue(any("prefix" in h.lower() for h in hints))


if __name__ == "__main__":
    unittest.main()
