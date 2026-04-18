"""
Deterministic semantic compression for huge schema registries (Phase D).

When a dataset exposes hundreds or thousands of similarly-shaped tables (e.g. per-ticker OHLC
in DuckDB), listing every name in routing / global-planner prompts wastes context. This module
summarizes those clusters using registry column shapes and ``intent_summary`` text only — no
benchmark-specific templates.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.utils import canonical_db_name


def _col_names_lower(row: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for c in row.get("columns") or []:
        if isinstance(c, dict) and c.get("name"):
            out.add(str(c["name"]).strip().lower())
    return out


def _is_ohlc_like(row: Dict[str, Any]) -> bool:
    """True when columns look like daily OHLCV price history."""
    cols = _col_names_lower(row)
    if not cols:
        return False
    has_ts = bool({"date", "timestamp", "trade_date"} & cols) or "date" in cols
    ohlc = sum(1 for k in ("open", "high", "low", "close") if k in cols)
    return has_ts and ohlc >= 4


def _is_listing_metadata(name: str, row: Dict[str, Any]) -> bool:
    n = name.lower()
    if n in {"stockinfo", "listing", "listings", "security_master"}:
        return True
    intent = str(row.get("intent_summary") or "").lower()
    return "listing" in intent and "exchange" in intent


def _is_index_trade(name: str, row: Dict[str, Any]) -> bool:
    n = name.lower()
    if "index" in n and "trade" in n:
        return True
    cols = _col_names_lower(row)
    return "index" in cols and bool({"open", "high", "low", "close"} & cols)


def _classify_table(name: str, row: Dict[str, Any]) -> str:
    if _is_listing_metadata(name, row):
        return "listing_metadata"
    if _is_index_trade(name, row):
        return "index_ohlc"
    if _is_ohlc_like(row):
        return "per_ticker_ohlc"
    intent = str(row.get("intent_summary") or "").lower()
    if any(k in intent for k in ("article", "corpus", "document collection", "mongodb")):
        return "text_corpus"
    if "metadata" in intent and "join" in intent:
        return "metadata"
    return "other"


def _gather_engine_rows(registry: Dict[str, Any], db: str) -> List[Tuple[str, Dict[str, Any]]]:
    out: List[Tuple[str, Dict[str, Any]]] = []
    eng: Optional[Dict[str, Any]] = None
    for eng_key, block in (registry.get("engines") or {}).items():
        if canonical_db_name(str(eng_key)) == db and isinstance(block, dict):
            eng = block
            break
    if not isinstance(eng, dict) or not eng.get("available"):
        return out
    for t in eng.get("tables") or []:
        if isinstance(t, dict) and t.get("name"):
            out.append((str(t["name"]), t))
    for c in eng.get("collections") or []:
        if isinstance(c, dict) and c.get("name"):
            out.append((str(c["name"]), c))
    return out


def build_compressed_registry_routing_text(
    registry: Dict[str, Any],
    available_databases: List[str],
    *,
    repo_root: Optional[Path] = None,
    max_example_names: int = 12,
    max_json_chars: int = 900,
) -> str:
    """
    Human-readable compressed summary. Always ends with registry path hint for exact-name lookup.
    """
    avail = sorted({canonical_db_name(x) for x in available_databases if canonical_db_name(str(x))})
    did = str(registry.get("dataset_id") or "").strip()
    lines: List[str] = []
    if did:
        lines.append(f"dataset_id={did}")
    lines.append(
        "SEMANTIC_SCHEMA_SUMMARY (compressed — many homogeneous tables grouped by column shape; "
        "use EXACT table/collection names from your selection or from the registry file when generating SQL)."
    )

    samples: Dict[str, List[str]] = {}

    for db in avail:
        rows = _gather_engine_rows(registry, db)
        if not rows:
            continue
        buckets: Dict[str, List[str]] = {}
        for name, row in rows:
            cat = _classify_table(name, row)
            buckets.setdefault(cat, []).append(name)

        lines.append(f"- {db}:")
        for cat in sorted(buckets.keys()):
            names = sorted(buckets[cat])
            if cat == "per_ticker_ohlc" and len(names) >= 12:
                ex = names[:max_example_names]
                samples[f"{db}_ohlc_examples"] = ex
                lines.append(
                    f"  • {cat}: {len(names)} tables — one table per ticker symbol; typical columns "
                    f"include Date, Open, High, Low, Close, Adj Close, Volume. "
                    f"Examples: {', '.join(ex)}{' …' if len(names) > len(ex) else ''}"
                )
            elif cat == "index_ohlc":
                lines.append(f"  • {cat}: {', '.join(names)}")
            elif cat == "listing_metadata":
                lines.append(f"  • {cat}: {', '.join(names)}")
            else:
                chunk = names[:40]
                more = len(names) - len(chunk)
                suf = f" (+{more} more)" if more > 0 else ""
                lines.append(f"  • {cat}: {', '.join(chunk)}{suf}")

    reg_path = ""
    if repo_root and did:
        reg_path = str(repo_root / "artifacts" / "schema_registry" / f"{did}.json")
    if samples:
        js = json.dumps({"exact_name_samples": samples}, ensure_ascii=False)
        if len(js) > max_json_chars:
            js = js[: max_json_chars - 3] + "..."
        lines.append(f"EXACT_NAME_SAMPLES_JSON: {js}")
    if reg_path:
        lines.append(f"FULL_REGISTRY_FILE (all exact names): {reg_path}")
    return "\n".join(lines)


def should_compress_registry(registry: Optional[Dict[str, Any]], available_databases: List[str]) -> bool:
    """Return True when total declared objects exceed the configured threshold."""
    if not registry:
        return False
    from utils.schema_registry.routing_compact import allowed_tables_by_database

    raw = os.getenv("ORACLE_FORGE_SEMANTIC_COMPRESS_MIN_NAMES")
    default_min = 48
    try:
        min_names = int(raw) if raw and raw.strip() else default_min
    except ValueError:
        min_names = default_min
    allowed = allowed_tables_by_database(registry)
    avail = {canonical_db_name(x) for x in available_databases if canonical_db_name(str(x))}
    total = sum(len(allowed.get(d, set())) for d in avail)
    return total >= min_names
