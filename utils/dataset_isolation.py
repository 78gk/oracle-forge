"""
Enforce that table/collection names never leave the active dataset's schema registry.

Used after routing (raw LLM ``selected_tables``) and after scoped schema bundle build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from agent.utils import canonical_db_name
from utils.schema_registry.routing_compact import allowed_tables_by_database


@dataclass
class DatasetIsolationError(RuntimeError):
    """A table/collection name is not declared for this dataset in ``artifacts/schema_registry``."""

    dataset_id: str
    phase: str
    offending: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""

    def __str__(self) -> str:
        return (
            f"DatasetIsolationError(dataset={self.dataset_id!r}, phase={self.phase!r}, "
            f"offending={self.offending!r})"
        )

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "phase": self.phase,
            "source": self.source,
            "offending": self.offending,
        }


def _names_in_metadata_engine(meta_db: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for key in ("tables", "collections"):
        for item in meta_db.get(key) or []:
            if isinstance(item, dict) and item.get("name"):
                out.add(str(item["name"]))
            elif isinstance(item, str):
                out.add(item)
    return out


def validate_schema_metadata_against_registry(
    registry: Dict[str, Any],
    schema_metadata: Dict[str, Any],
    *,
    dataset_id: str,
    phase: str,
    source: str = "schema_metadata",
) -> None:
    """Every table/collection name in ``schema_metadata`` must appear in the registry for that engine."""
    allowed = allowed_tables_by_database(registry)
    did = str(registry.get("dataset_id") or dataset_id).strip()
    offending: List[Dict[str, Any]] = []
    for db_raw, meta in (schema_metadata or {}).items():
        if str(db_raw).startswith("_"):
            continue
        db = canonical_db_name(str(db_raw))
        if not isinstance(meta, dict):
            continue
        reg = allowed.get(db)
        if not reg:
            continue
        for n in _names_in_metadata_engine(meta):
            if n not in reg:
                offending.append({"engine": db, "object": n, "reason": "not_in_registry"})
    if offending:
        raise DatasetIsolationError(dataset_id=did, phase=phase, offending=offending, source=source)


def validate_routing_selected_tables(
    registry: Dict[str, Any],
    selected_tables_raw: Any,
    available_databases: List[str],
    *,
    dataset_id: str,
    phase: str = "routing",
    source: str = "llm_routing.selected_tables",
) -> None:
    """
    Raw routing output must not name objects outside the registry.
    Call **before** filtering down to registry (silent drops hide bugs).
    """
    if not isinstance(selected_tables_raw, dict):
        return
    allowed = allowed_tables_by_database(registry)
    avail = {canonical_db_name(x) for x in available_databases if canonical_db_name(str(x))}
    did = str(registry.get("dataset_id") or dataset_id).strip()
    offending: List[Dict[str, Any]] = []
    for raw_db, names in selected_tables_raw.items():
        db = canonical_db_name(str(raw_db))
        if db not in avail:
            continue
        reg = allowed.get(db)
        if not reg:
            continue
        if not isinstance(names, list):
            continue
        for item in names:
            n = str(item).strip()
            if n and n not in reg:
                offending.append({"engine": db, "object": n, "reason": "routing_named_unknown_object"})
    if offending:
        raise DatasetIsolationError(dataset_id=did, phase=phase, offending=offending, source=source)


def validate_schema_bundle_objects(
    registry: Dict[str, Any],
    bundle: Dict[str, Any],
    *,
    dataset_id: str,
    phase: str = "scoped_schema_bundle",
    source: str = "schema_bundle",
) -> None:
    """Validate ``build_scoped_schema_bundle`` / ``build_schema_bundle`` engine payloads."""
    allowed = allowed_tables_by_database(registry)
    did = str(registry.get("dataset_id") or dataset_id).strip()
    offending: List[Dict[str, Any]] = []
    engines = bundle.get("engines") or {}
    if not isinstance(engines, dict):
        return
    for db_raw, block in engines.items():
        db = canonical_db_name(str(db_raw))
        reg = allowed.get(db)
        if not reg:
            continue
        if not isinstance(block, dict):
            continue
        for key in ("tables", "collections"):
            for item in block.get(key) or []:
                if not isinstance(item, dict):
                    continue
                n = str(item.get("name") or "").strip()
                if n and n not in reg:
                    offending.append({"engine": db, "object": n, "kind": key, "reason": "bundle_name_not_in_registry"})
    if offending:
        raise DatasetIsolationError(dataset_id=did, phase=phase, offending=offending, source=source)


def isolation_enabled() -> bool:
    import os

    raw = os.getenv("ORACLE_FORGE_DATASET_ISOLATION")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}
