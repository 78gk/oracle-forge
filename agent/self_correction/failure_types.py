"""Failure taxonomy aligned with tool errors and planner replan signals."""

from __future__ import annotations

from enum import Enum


class FailureFamily(str, Enum):
    """High-level groups for recovery routing."""

    JOIN = "join"
    SCHEMA = "schema"
    DIALECT = "dialect"
    TOOL_ROUTING = "tool_routing"
    SAFETY = "safety"
    UNKNOWN = "unknown"


def normalize_error_type(raw: str | None) -> FailureFamily:
    """Map MCP / executor ``error_type`` strings into a small family set."""
    ft = (raw or "unknown_error").strip().lower()
    if ft in {"join_mismatch", "join_key_mismatch"}:
        return FailureFamily.JOIN
    if ft in {"schema_mismatch", "schema_error", "need_schema_refresh"}:
        return FailureFamily.SCHEMA
    if ft in {"sql_dialect_error", "dialect_error"}:
        return FailureFamily.DIALECT
    if ft in {"tool_routing_error"}:
        return FailureFamily.TOOL_ROUTING
    if ft in {"unsafe_sql"}:
        return FailureFamily.SAFETY
    return FailureFamily.UNKNOWN
