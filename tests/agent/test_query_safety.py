from __future__ import annotations

import pytest

from agent.query_safety import validate_sql, validate_mongo_pipeline, validate_step_payload


@pytest.fixture(autouse=True)
def _strict_sql_columns_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORACLE_FORGE_STRICT_SQL_COLUMNS", "true")


def test_validate_sql_blocks_ddl() -> None:
    ok, msg = validate_sql("postgresql", "DROP TABLE business", {})
    assert not ok
    assert "forbidden" in msg.lower() or msg.startswith("forbidden")


def test_validate_sql_allows_select() -> None:
    schema = {"postgresql": {"tables": [{"name": "business"}, {"name": "review"}]}}
    ok, msg = validate_sql("postgresql", 'SELECT * FROM business LIMIT 5', schema)
    assert ok


def test_validate_sql_unknown_table_when_strict() -> None:
    schema = {"postgresql": {"tables": [{"name": "business"}]}}
    ok, msg = validate_sql("postgresql", "SELECT * FROM phantom LIMIT 1", schema)
    assert not ok
    assert "unknown" in msg.lower()


def test_validate_mongo_collection() -> None:
    schema = {"mongodb": {"collections": [{"name": "business"}]}}
    ok, _ = validate_mongo_pipeline("mongodb", "business", [{"$limit": 10}], schema)
    assert ok


def test_validate_step_payload_sql() -> None:
    step = {
        "database": "postgresql",
        "dialect": "sql",
        "query_payload": {"sql": "SELECT 1", "database": "postgresql", "dialect": "sql", "question": "q"},
    }
    ok, _ = validate_step_payload(step, {})
    assert ok


def test_validate_sql_strict_rejects_wrong_column_name() -> None:
    schema = {
        "postgresql": {
            "tables": [{"name": "review", "fields": {"stars": "integer", "business_id": "text"}}]
        }
    }
    ok, msg = validate_sql("postgresql", "SELECT r.rating FROM review AS r", schema)
    assert not ok
    assert "unknown_columns" in msg


def test_validate_sql_strict_allows_qualified_correct_column() -> None:
    schema = {
        "postgresql": {
            "tables": [{"name": "review", "fields": {"stars": "integer", "business_id": "text"}}]
        }
    }
    ok, msg = validate_sql("postgresql", "SELECT r.stars FROM review AS r LIMIT 5", schema)
    assert ok


def test_validate_sql_cte_name_not_treated_as_unknown_table() -> None:
    """CTE aliases must not be flagged as missing physical tables."""
    schema = {
        "postgresql": {
            "tables": [
                {"name": "business", "fields": {"business_id": "text", "state_code": "text"}},
                {"name": "review", "fields": {"stars": "integer", "business_id": "text"}},
            ]
        }
    }
    sql = """
    WITH state_counts AS (
      SELECT b.state_code, COUNT(*) AS c
      FROM business b
      JOIN review r ON r.business_id = b.business_id
      GROUP BY b.state_code
    )
    SELECT state_code, c FROM state_counts ORDER BY c DESC LIMIT 1
    """
    ok, msg = validate_sql("postgresql", sql, schema)
    assert ok, msg


def test_validate_sql_rejects_text_column_vs_date_literal() -> None:
    schema = {
        "postgresql": {
            "tables": [{"name": "review", "fields": {"date": "text", "stars": "integer"}}]
        }
    }
    bad = "SELECT 1 FROM review r WHERE r.date >= DATE '2018-01-01'"
    ok, msg = validate_sql("postgresql", bad, schema)
    assert not ok
    assert "text_date_compare" in msg
    good = "SELECT 1 FROM review r WHERE (r.date)::date >= DATE '2018-01-01'"
    assert validate_sql("postgresql", good, schema)[0]


def test_validate_llm_generated_steps_flat_sql() -> None:
    from agent.query_safety import validate_llm_generated_steps

    schema = {
        "postgresql": {
            "tables": [{"name": "review", "fields": {"stars": "integer", "business_id": "text"}}]
        }
    }
    steps = [
        {
            "database": "postgresql",
            "dialect": "sql",
            "sql": "SELECT AVG(stars) FROM review",
        }
    ]
    ok, errs = validate_llm_generated_steps(steps, schema)
    assert ok
    assert errs == []

    steps_bad = [
        {
            "database": "postgresql",
            "dialect": "sql",
            "sql": "SELECT AVG(rating) FROM review",
        }
    ]
    ok2, errs2 = validate_llm_generated_steps(steps_bad, schema)
    assert not ok2
    assert any("unknown_columns" in e for e in errs2)
