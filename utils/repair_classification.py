"""
Classify repair attempts as syntax/runtime (patch SQL/dialect) vs semantic (re-plan scope/joins).

Phase F — used by QueryPlanner for pre-exec repair and closed-loop execution replans.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Literal, Optional, Sequence

RepairClass = Literal["syntax", "semantic"]


def semantic_global_refresh_enabled() -> bool:
    """When true, semantic-class failures may refresh ``context[\"global_plan\"]`` once per stage."""
    raw = os.getenv("ORACLE_FORGE_SEMANTIC_GLOBAL_REFRESH")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def classify_preexec_failure(
    gen_out: Optional[Dict[str, Any]],
    *,
    repair_notes: Optional[Sequence[str]] = None,
) -> RepairClass:
    """
    Pre-execution: generator / schema gate failures before tools run.

    Semantic: wrong readiness, missing join scope, empty plan when structure expected.
    Syntax: parser-level generation failures, dialect surface errors in model output.
    """
    notes = " ".join(str(x) for x in (repair_notes or ()) if x)
    combined = notes.lower()
    if gen_out is None:
        return "semantic"
    if not isinstance(gen_out, dict):
        return "syntax"
    if gen_out.get("schema_gate_failed"):
        gd = str(gen_out.get("gate_detail") or "").lower()
        if any(k in gd for k in ("readiness", "join", "missing table", "wrong engine", "scope")):
            return "semantic"
        return "syntax"
    if gen_out.get("generation_failed"):
        gd = str(gen_out.get("gate_detail") or "").lower()
        if any(k in gd for k in ("parse", "syntax", "invalid", "token", "binder")):
            return "syntax"
        return "semantic"
    st = gen_out.get("steps")
    if isinstance(st, list) and not st:
        return "semantic"
    if "plan_mapping_failed" in combined:
        return "semantic"
    return "syntax"


def classify_execution_failure(failure_types: Sequence[str], step_errors: Sequence[str]) -> RepairClass:
    """Post-tool: classify whether to patch SQL vs re-plan analytical intent."""
    fts = {str(x).strip().lower() for x in failure_types if x}
    err_blob = " ".join(str(e) for e in step_errors).lower()
    if fts & {"join_key_mismatch", "tool_routing_error"}:
        return "semantic"
    if "join" in err_blob and ("mismatch" in err_blob or "key" in err_blob):
        return "semantic"
    if fts & {"dialect_error", "execution_error"}:
        return "syntax"
    if fts & {"schema_error"}:
        if re.search(r"\b(alias|wrong table|missing from)\b", err_blob):
            return "semantic"
        return "syntax"
    if fts & {"unsafe_sql"}:
        return "syntax"
    return "syntax"
