"""Self-correction: failure taxonomy and recovery routing."""

from .failure_types import FailureFamily, normalize_error_type
from .recovery_router import RecoveryDecision, recommend_recovery

__all__ = [
    "FailureFamily",
    "RecoveryDecision",
    "normalize_error_type",
    "recommend_recovery",
]
