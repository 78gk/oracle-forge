#!/usr/bin/env python3
"""Verify SQLite/DuckDB paths from DataAgentBench query_*/db_config.yaml exist and open."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAB = REPO / "DataAgentBench"


def _parse_local_paths() -> list[tuple[str, str, Path]]:
    out: list[tuple[str, str, Path]] = []
    for cfg in sorted(DAB.glob("query_*/db_config.yaml")):
        ds = cfg.parent.name
        cur: str | None = None
        for line in cfg.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("db_type:"):
                cur = s.split(":", 1)[1].strip().split()[0].lower()
            elif s.startswith("db_path:") and cur in ("sqlite", "duckdb"):
                rel = s.split(":", 1)[1].strip().split()[0]
                out.append((ds, cur, (cfg.parent / rel).resolve()))
    return out


def _sqlite_tables(p: Path) -> list[str]:
    con = sqlite3.connect(str(p))
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def _duck_tables(p: Path) -> list[str]:
    import duckdb

    con = duckdb.connect(str(p), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def main() -> int:
    try:
        import duckdb  # noqa: F401
    except ImportError:
        print("Install duckdb to validate DuckDB files: pip install duckdb", file=sys.stderr)
        return 1

    rows = _parse_local_paths()
    missing: list[Path] = []
    print("Dataset                Kind   Status   Tables  File")
    print("-" * 88)
    for ds, kind, p in rows:
        if not p.is_file():
            print(f"{ds:22} {kind:6} MISSING  -       {p.name}")
            missing.append(p)
            continue
        try:
            if kind == "sqlite":
                t = _sqlite_tables(p)
            else:
                t = _duck_tables(p)
            print(f"{ds:22} {kind:6} OK       {len(t):5d}   {p.name}")
        except OSError as exc:
            print(f"{ds:22} {kind:6} FAIL     -       {p.name} ({exc})")
            missing.append(p)

    print("-" * 88)
    if missing:
        print(f"Problems: {len(missing)} file(s) missing or unreadable.")
        return 1
    print("All SQLite/DuckDB paths from db_config exist and opened cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
