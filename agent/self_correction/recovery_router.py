"""Maps failure signals to human-readable recovery strategies (fork-style recovery router)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from utils.repair_classification import RepairClass, classify_execution_failure

from .failure_types import FailureFamily, normalize_error_type


@dataclass
class RecoveryDecision:
    """Hints consumed by :class:`~agent.planner.QueryPlanner` during replan."""

    correction_notes: List[str] = field(default_factory=list)
    execution_repair_class: RepairClass = "syntax"


def recommend_recovery(
    failure_types: Sequence[str],
    step_errors: Sequence[str],
) -> RecoveryDecision:
    """
    Produce structured recovery guidance from raw step failures.

    Keeps parity with prior inline notes in ``QueryPlanner._replan_with_corrections`` while
    centralizing the mapping for logging and future extension.
    """
    fts = [str(x).strip() for x in failure_types if str(x).strip()]
    raw_errs = [str(err).strip() for err in step_errors if str(err).strip()]
    ex_kind = classify_execution_failure(fts, raw_errs)
    notes: List[str] = []

    families = {normalize_error_type(ft) for ft in fts}
    if FailureFamily.JOIN in families:
        notes.append("Replan with join-key normalization strategy from v3 corrections.")
    if FailureFamily.SCHEMA in families:
        notes.append("Replan with stricter schema introspection table/field selection.")
    if FailureFamily.DIALECT in families:
        notes.append("Replan enforcing dialect constraints from v1 architecture layer.")
    if FailureFamily.TOOL_ROUTING in families:
        notes.append("Replan with explicit database-tool compatibility constraints.")
    if FailureFamily.SAFETY in families:
        notes.append("Regenerate read-only SQL or Mongo pipeline; respect schema allowlist.")
    if not notes:
        notes.append("Generic replan based on prior failures and resolved patterns.")

    return RecoveryDecision(correction_notes=notes, execution_repair_class=ex_kind)
