"""
autoDream-style consolidation: fold runtime failure logs into ``kb/corrections/resolved_patterns.md``.

See ``kb/architecture/autodream_consolidation.md``. Run weekly or when the log exceeds the threshold.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, List


DEFAULT_THRESHOLD = 50
RUNTIME_LOG = "docs/driver_notes/runtime_corrections.jsonl"
OUTPUT_REL = "kb/corrections/resolved_patterns.md"


def _repo_root(start: Path | None = None) -> Path:
    return (start or Path(__file__).resolve().parents[1])


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def consolidate(
    repo_root: Path | None = None,
    *,
    force: bool = False,
    threshold: int = DEFAULT_THRESHOLD,
) -> bool:
    """
    Append a consolidated section when ``runtime_corrections.jsonl`` has at least ``threshold`` lines
    (or when ``force`` is true). Returns True if the KB file was updated.
    """
    root = _repo_root(repo_root)
    src = root / RUNTIME_LOG
    out = root / OUTPUT_REL
    lines = _read_jsonl(src)
    if not lines:
        return False
    if not force and len(lines) < threshold:
        return False

    by_type: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in lines:
        ft = str(row.get("failure_type") or "unknown_error")
        by_type[ft].append(row)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    block_lines = [
        "",
        f"## autoDream consolidation — {stamp}",
        f"**Source:** `{RUNTIME_LOG}` ({len(lines)} rows)",
        "",
    ]
    for ft, items in sorted(by_type.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        block_lines.append(f"### Failure type: `{ft}` (n={len(items)})")
        sample = items[-3:]
        for row in sample:
            q = str(row.get("question") or "")[:200]
            err = str(row.get("sanitized_error") or "")[:300]
            block_lines.append(f"- Q: {q}")
            block_lines.append(f"  - {err}")
        block_lines.append("")

    block = "\n".join(block_lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.is_file():
        out.write_text("# Resolved Patterns\n\n", encoding="utf-8")
    with out.open("a", encoding="utf-8") as handle:
        handle.write(block)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate runtime corrections into resolved_patterns.md")
    parser.add_argument("--force", action="store_true", help="Run even below the entry threshold.")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, metavar="N", help="Minimum JSONL rows.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Oracle Forge repo root (default: parent of utils/).",
    )
    args = parser.parse_args()
    updated = consolidate(args.repo_root or _repo_root(), force=args.force, threshold=args.threshold)
    print("updated resolved_patterns.md" if updated else "no update (below threshold or empty log)")


if __name__ == "__main__":
    main()
