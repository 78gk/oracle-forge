"""
PostgreSQL templates for DataAgentBench `query_yelp` (exact `query.json` question strings).

Templates match `scripts/seed_yelp_postgres.py` (derived `state_code`, `business_category`, flags).
Reconcile ground truth: `python scripts/reconcile_yelp_ground_truth.py`.
"""
from __future__ import annotations

from typing import Dict, Optional

POSTGRES_SQL_BY_QUESTION: Dict[str, str] = {
    "What is the average rating of all businesses located in Indianapolis, Indiana?": """
SELECT AVG(r.stars::double precision) AS avg_rating
FROM review r
JOIN business b ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
WHERE b.description ILIKE '%Indianapolis%'
  AND b.description LIKE '%, IN%'
""",
    "Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state?": """
WITH joined AS (
  SELECT b.state_code AS st, r.stars::double precision AS s
  FROM review r
  JOIN business b ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
  WHERE b.state_code IS NOT NULL AND b.state_code <> ''
), agg AS (
  SELECT st, COUNT(*)::bigint AS n, AVG(s) AS avg_rating
  FROM joined GROUP BY st
), top AS (
  SELECT st FROM agg ORDER BY n DESC LIMIT 1
)
SELECT a.st, a.avg_rating FROM agg a INNER JOIN top t ON a.st = t.st
""",
    "During 2018, how many businesses that received reviews offered either business parking or bike parking?": """
SELECT COUNT(DISTINCT b.business_id)::bigint AS cnt
FROM business b
JOIN review r ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
WHERE r.date LIKE '%2018%'
  AND (
    b.attributes LIKE '%''BikeParking'': ''True''%'
    OR b.attributes ~ 'BusinessParking.*(garage|street|validated|lot|valet)'': True'
  )
""",
    "Which business category has the largest number of businesses that accept credit card payments, and what is its average rating?": """
WITH joined AS (
  SELECT
    CASE WHEN bc.category = 'Restaurants' THEN 'Restaurant' ELSE bc.category END AS cat,
    b.business_id AS bid,
    r.stars::double precision AS s
  FROM business b
  INNER JOIN business_category bc ON bc.business_id = b.business_id
  INNER JOIN review r ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
  WHERE b.accepts_credit_cards
), agg AS (
  SELECT cat, COUNT(DISTINCT bid)::bigint AS n, AVG(s) AS avg_rating
  FROM joined GROUP BY cat
), top AS (
  SELECT cat FROM agg ORDER BY n DESC, cat ASC LIMIT 1
)
SELECT a.cat, a.avg_rating FROM agg a INNER JOIN top t ON a.cat = t.cat
""",
    "Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses?": """
WITH ws AS (
  SELECT business_id, state_code
  FROM business
  WHERE has_wifi AND state_code IS NOT NULL AND state_code <> ''
), sc AS (
  SELECT state_code, COUNT(DISTINCT business_id)::bigint AS n
  FROM ws
  GROUP BY state_code
), top AS (
  SELECT state_code FROM sc ORDER BY n DESC LIMIT 1
), j AS (
  SELECT r.stars::double precision AS s
  FROM review r
  JOIN business b ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
  WHERE b.business_id IN (SELECT business_id FROM ws WHERE state_code = (SELECT state_code FROM top))
)
SELECT (SELECT state_code FROM top) AS st, (SELECT AVG(s) FROM j) AS avg_rating
""",
    "Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews.": """
WITH bounds AS (
  SELECT business_id,
         AVG(stars::double precision) AS avg_s,
         COUNT(*)::bigint AS n
  FROM review
  WHERE date >= '2016-01-01' AND date <= '2016-06-30'
  GROUP BY business_id
  HAVING COUNT(*) >= 5
), winner AS (
  SELECT business_id FROM bounds ORDER BY avg_s DESC, business_id ASC LIMIT 1
)
SELECT (trim(b.name) || ',' || replace(COALESCE(b.primary_categories, ''), '|', ',')) AS full_line
FROM business b
WHERE b.business_id = (SELECT business_id FROM winner)
""",
    "Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016?": """
WITH u2016 AS (
  SELECT user_id FROM "user" WHERE yelping_since LIKE '2016%'
), tagged AS (
  SELECT bc.category
  FROM review r
  INNER JOIN u2016 ON r.user_id = u2016.user_id
  INNER JOIN business b ON r.business_id = REPLACE(b.business_id, 'businessid_', 'businessref_')
  INNER JOIN business_category bc ON bc.business_id = b.business_id
  WHERE r.date >= '2016-01-01'
), agg AS (
  SELECT category, COUNT(*)::bigint AS n
  FROM tagged
  GROUP BY category
)
SELECT category FROM agg ORDER BY n DESC, category ASC LIMIT 5
""",
}


def postgres_sql_for_yelp_question(question: str) -> Optional[str]:
    text = (question or "").strip()
    sql = POSTGRES_SQL_BY_QUESTION.get(text)
    if sql:
        return " ".join(sql.split())
    return None


def is_yelp_template_question(question: str) -> bool:
    return postgres_sql_for_yelp_question(question) is not None
