"""Structured repair hints for query regeneration (stable across retries)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RepairPacket:
    """Machine-oriented repair instruction; serialize with ``to_prompt_line``."""

    error_type: str
    failing_identifier: Optional[str] = None
    allowed_tables: Optional[List[str]] = None
    known_columns: Optional[Dict[str, List[str]]] = None
    ctes_allowed: bool = True
    engine: Optional[str] = None
    hint: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_line(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if v not in (None, "", [], {})}
        return "repair_packet:" + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def from_line(line: str) -> Optional["RepairPacket"]:
        s = line.strip()
        if not s.startswith("repair_packet:"):
            return None
        try:
            data = json.loads(s[len("repair_packet:") :].strip())
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return RepairPacket(
            error_type=str(data.get("error_type", "unknown")),
            failing_identifier=data.get("failing_identifier"),
            allowed_tables=data.get("allowed_tables"),
            known_columns=data.get("known_columns"),
            ctes_allowed=bool(data.get("ctes_allowed", True)),
            engine=data.get("engine"),
            hint=str(data.get("hint", "")),
            extra={k: v for k, v in data.items() if k not in {"error_type", "failing_identifier", "allowed_tables", "known_columns", "ctes_allowed", "engine", "hint"}},
        )


def split_repair_and_legacy_notes(notes: List[str]) -> tuple[List[str], List[str]]:
    """Partition ``repair_packet:`` lines vs legacy prose."""
    repair: List[str] = []
    legacy: List[str] = []
    for n in notes:
        if str(n).strip().startswith("repair_packet:"):
            repair.append(str(n).strip())
        else:
            legacy.append(n)
    return repair, legacy
