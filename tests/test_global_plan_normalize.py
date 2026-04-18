"""Phase E: normalize_global_plan_payload."""

from __future__ import annotations

from agent.query_pipeline import format_global_plan_contract_for_prompt, normalize_global_plan_payload


def test_normalize_grain_grouped_to_per_group() -> None:
    gp = {"output_contract": {"grain": "grouped"}}
    out = normalize_global_plan_payload(gp)
    assert out["output_contract"]["grain"] == "per_group"


def test_normalize_result_shape_grouped_to_per_group() -> None:
    gp = {"output_contract": {"grain": "per_group", "result_shape": "grouped"}}
    out = normalize_global_plan_payload(gp)
    assert out["output_contract"]["result_shape"] == "per_group"
    assert out["output_contract"]["grain"] == "per_group"


def test_normalize_result_shape_grouped_upgrades_scalar_grain() -> None:
    gp = {"output_contract": {"grain": "scalar", "result_shape": "grouped"}}
    out = normalize_global_plan_payload(gp)
    assert out["output_contract"]["result_shape"] == "per_group"
    assert out["output_contract"]["grain"] == "per_group"


def test_normalize_top_k_from_ranking() -> None:
    gp = {"output_contract": {"requires_ranking": True}, "ranking": {"k": 5}}
    out = normalize_global_plan_payload(gp)
    assert out["output_contract"]["top_k"] == 5


def test_format_contract_non_degraded() -> None:
    gp = {
        "target_entity": "t",
        "output_contract": {"grain": "scalar", "result_shape": "scalar"},
    }
    s = format_global_plan_contract_for_prompt(gp)
    assert "target_entity" in s and "output_contract" in s
