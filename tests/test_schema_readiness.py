from agent.query_pipeline import phase_schema_link
from utils.schema_readiness import schema_gate_sql_tables


def test_schema_gate_fails_when_columns_empty() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business", "fields": {}},
            ]
        }
    }
    ok, msg = schema_gate_sql_tables("postgresql", meta, ["business"])
    assert not ok
    assert "need_schema_refresh" in msg


def test_schema_gate_passes_with_columns() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business", "fields": {"business_id": "text"}},
            ]
        }
    }
    ok, msg = schema_gate_sql_tables("postgresql", meta, ["business"])
    assert ok
    assert msg == ""


def test_phase_schema_link_passes_and_returns_json() -> None:
    meta = {
        "postgresql": {
            "tables": [
                {"name": "business", "fields": {"business_id": "text"}},
            ]
        }
    }
    scoped = {"postgresql": {"tables": [{"name": "business", "fields": {"business_id": "text"}}]}}
    payload, err = phase_schema_link("postgresql", ["business"], scoped, meta, max_json_chars=5000)
    assert err == ""
    assert payload is not None
    assert payload.readiness_ok
    assert "business" in payload.linked_schema_json
