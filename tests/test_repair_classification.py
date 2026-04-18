"""Phase F: repair classification."""

from __future__ import annotations

from utils.repair_classification import (
    classify_execution_failure,
    classify_preexec_failure,
)


def test_preexec_schema_gate_semantic() -> None:
    assert (
        classify_preexec_failure({"schema_gate_failed": True, "gate_detail": "readiness: missing join"})
        == "semantic"
    )


def test_preexec_generation_syntax_hint() -> None:
    assert (
        classify_preexec_failure(
            {"generation_failed": True, "gate_detail": "Parser error: invalid token near SELECT"}
        )
        == "syntax"
    )


def test_execution_join_mismatch_semantic() -> None:
    assert classify_execution_failure(["join_key_mismatch"], ["keys do not align"]) == "semantic"


def test_execution_dialect_syntax() -> None:
    assert classify_execution_failure(["dialect_error"], ["syntax error near FROM"]) == "syntax"


def test_preexec_plan_mapping_notes_semantic() -> None:
    assert (
        classify_preexec_failure(
            {"steps": [{"database": "x"}]},
            repair_notes=["preexec: plan_mapping_failed: incomplete"],
        )
        == "semantic"
    )
