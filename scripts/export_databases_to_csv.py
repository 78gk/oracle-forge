#!/usr/bin/env python3
"""
Export all tables/collections from Postgres, MongoDB, SQLite, and DuckDB to:

  database_export/<engine>/<name>/data.csv

Uses .env (POSTGRES_DSN, MONGODB_URI, MONGODB_DATABASE, SQLITE_PATH, DUCKDB_PATH).
If Postgres/Mongo refuse localhost, tries `docker exec` against oracle-forge-mcp-* containers.

Run from repo root:  python scripts/export_databases_to_csv.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
EXPORT_ROOT = REPO / "database_export"
MAX_ROWS = int(os.getenv("DATABASE_EXPORT_MAX_ROWS", "200000"))


def _safe_segment(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("_") or "unknown"


def _write_csv(path: Path, headers: List[str], rows: List[List[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow(row)


def _mongo_flatten(doc: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in doc.items():
        if k == "_id":
            out["_id"] = str(v)
        elif isinstance(v, (dict, list)):
            out[str(k)] = json.dumps(v, ensure_ascii=False, default=str)
        else:
            out[str(k)] = v
    return out


async def export_postgres_async(dsn: str) -> bool:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        tables = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        for r in tables:
            t = r["table_name"]
            if t.startswith("pg_"):
                continue
            # Quote reserved names like "user"
            ident = f'"{t}"' if not t.isidentifier() or t.lower() == "user" else t
            rows = await conn.fetch(f"SELECT * FROM {ident} LIMIT {MAX_ROWS}")
            if not rows:
                colrows = await conn.fetch(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY ordinal_position
                    """,
                    t,
                )
                colnames = [c["column_name"] for c in colrows]
                _write_csv(
                    EXPORT_ROOT / "postgresql" / _safe_segment(t) / "data.csv",
                    colnames or ["(empty)"],
                    [],
                )
                continue
            cols = list(rows[0].keys())
            data = [[row[c] for c in cols] for row in rows]
            _write_csv(EXPORT_ROOT / "postgresql" / _safe_segment(t) / "data.csv", cols, data)
        return True
    finally:
        await conn.close()


def export_postgres_docker() -> bool:
    """COPY each public table via docker exec + psql."""
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        return False
    names = [n.strip() for n in out.stdout.splitlines() if n.strip()]
    pg = next((n for n in names if "postgres" in n.lower() and "oracle" in n.lower()), None)
    if not pg:
        pg = next((n for n in names if "postgres" in n.lower()), None)
    if not pg:
        return False

    # List tables
    ls = subprocess.run(
        [
            "docker",
            "exec",
            pg,
            "psql",
            "-U",
            "postgres",
            "-d",
            "oracleforge",
            "-At",
            "-c",
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
            "AND table_type='BASE TABLE' ORDER BY 1",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if ls.returncode != 0:
        print(f"[postgres docker] list tables failed: {ls.stderr}", file=sys.stderr)
        return False
    tables = [x.strip() for x in ls.stdout.splitlines() if x.strip()]
    for t in tables:
        ident = f'"{t}"' if t.lower() == "user" or not t.replace("_", "").isalnum() else t
        cp = subprocess.run(
            [
                "docker",
                "exec",
                pg,
                "psql",
                "-U",
                "postgres",
                "-d",
                "oracleforge",
                "-c",
                f"COPY (SELECT * FROM {ident} LIMIT {MAX_ROWS}) TO STDOUT WITH (FORMAT csv, HEADER true)",
            ],
            capture_output=True,
            timeout=300,
        )
        if cp.returncode != 0:
            print(f"[postgres docker] copy {t}: {cp.stderr.decode('utf-8', errors='replace')}", file=sys.stderr)
            continue
        dest = EXPORT_ROOT / "postgresql" / _safe_segment(t) / "data.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(cp.stdout)
    return True


def export_mongo(uri: str, db_name: str) -> bool:
    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        for name in sorted(db.list_collection_names()):
            if name.startswith("system."):
                continue
            docs = list(db[name].find().limit(MAX_ROWS))
            if not docs:
                _write_csv(EXPORT_ROOT / "mongodb" / _safe_segment(name) / "data.csv", ["(empty)"], [])
                continue
            flat = [_mongo_flatten(d) for d in docs]
            cols = sorted({k for d in flat for k in d.keys()})
            rows = [[d.get(c, "") for c in cols] for d in flat]
            _write_csv(EXPORT_ROOT / "mongodb" / _safe_segment(name) / "data.csv", cols, rows)
        return True
    finally:
        client.close()


def export_mongo_docker(db_name: str) -> bool:
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        return False
    names = [n.strip() for n in out.stdout.splitlines() if n.strip()]
    mc = next((n for n in names if "mongo" in n.lower() and "seed" not in n.lower()), None)
    if not mc:
        mc = next((n for n in names if "mongo" in n.lower()), None)
    if not mc:
        return False

    ls = subprocess.run(
        [
            "docker",
            "exec",
            mc,
            "mongosh",
            db_name,
            "--quiet",
            "--eval",
            "db.getCollectionNames().filter(c => !c.startsWith('system.')).join('\\n')",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if ls.returncode != 0:
        print(f"[mongo docker] list collections: {ls.stderr}", file=sys.stderr)
        return False
    collections = [c.strip() for c in ls.stdout.splitlines() if c.strip()]
    for coll in collections:
        js = (
            f"const rows = db.getCollection('{coll}').find().limit({MAX_ROWS}).toArray(); "
            "print(JSON.stringify(rows));"
        )
        m = subprocess.run(
            ["docker", "exec", mc, "mongosh", db_name, "--quiet", "--eval", js],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if m.returncode != 0:
            print(f"[mongo docker] {coll}: {m.stderr}", file=sys.stderr)
            continue
        try:
            arr = json.loads(m.stdout.strip())
        except json.JSONDecodeError:
            print(f"[mongo docker] {coll}: invalid JSON", file=sys.stderr)
            continue
        if not arr:
            _write_csv(EXPORT_ROOT / "mongodb" / _safe_segment(coll) / "data.csv", ["(empty)"], [])
            continue
        flat = [_mongo_flatten(d) for d in arr]
        cols = sorted({k for d in flat for k in d.keys()})
        rows = [[d.get(c, "") for c in cols] for d in flat]
        _write_csv(EXPORT_ROOT / "mongodb" / _safe_segment(coll) / "data.csv", cols, rows)
    return True


def export_sqlite(path: Path) -> bool:
    import sqlite3

    if not path.exists():
        print(f"[sqlite] missing file: {path}", file=sys.stderr)
        return False
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f'SELECT * FROM "{t}"' if not t.isidentifier() else f"SELECT * FROM {t}")
        rows = cur.fetchmany(MAX_ROWS)
        cols = [d[0] for d in cur.description] if cur.description else []
        data = [list(r) for r in rows]
        _write_csv(EXPORT_ROOT / "sqlite" / _safe_segment(t) / "data.csv", cols, data)
    con.close()
    return True


def export_duckdb(path: Path) -> bool:
    import duckdb

    if not path.exists():
        print(f"[duckdb] missing file: {path}", file=sys.stderr)
        return False
    con = duckdb.connect(str(path), read_only=True)
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    for (t,) in tables:
        ident = f'"{t}"' if t.lower() == "user" else t
        res = con.execute(f"SELECT * FROM {ident} LIMIT {MAX_ROWS}")
        cols = [d[0] for d in res.description]
        rows = res.fetchall()
        data = [list(r) for r in rows]
        _write_csv(EXPORT_ROOT / "duckdb" / _safe_segment(t) / "data.csv", cols, data)
    con.close()
    return True


def main() -> int:
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env", override=False)
    except ImportError:
        pass

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    dsn = (os.getenv("POSTGRES_DSN") or "").strip()
    mongo_uri = (os.getenv("MONGODB_URI") or "").strip()
    mongo_db = (os.getenv("MONGODB_DATABASE") or "yelp_db").strip()
    sqlite_path = Path((os.getenv("SQLITE_PATH") or "").strip() or REPO / "DataAgentBench/query_bookreview/query_dataset/review_query.db")
    duck_path = Path((os.getenv("DUCKDB_PATH") or "").strip() or REPO / "DataAgentBench/query_yelp/query_dataset/yelp_user.db")
    if not sqlite_path.is_absolute():
        sqlite_path = (REPO / sqlite_path).resolve()
    if not duck_path.is_absolute():
        duck_path = (REPO / duck_path).resolve()

    ok_pg = False
    if dsn:
        try:
            asyncio.run(export_postgres_async(dsn))
            ok_pg = True
            print(f"[postgresql] exported to {EXPORT_ROOT / 'postgresql'}")
        except Exception as exc:
            print(f"[postgresql] direct failed: {exc}", file=sys.stderr)
            if export_postgres_docker():
                ok_pg = True
                print(f"[postgresql] exported via docker -> {EXPORT_ROOT / 'postgresql'}")
            else:
                print("[postgresql] skipped", file=sys.stderr)

    ok_m = False
    if mongo_uri:
        try:
            export_mongo(mongo_uri, mongo_db)
            ok_m = True
            print(f"[mongodb] exported to {EXPORT_ROOT / 'mongodb'}")
        except Exception as exc:
            print(f"[mongodb] direct failed: {exc}", file=sys.stderr)
            if export_mongo_docker(mongo_db):
                ok_m = True
                print(f"[mongodb] exported via docker -> {EXPORT_ROOT / 'mongodb'}")
            else:
                print("[mongodb] skipped", file=sys.stderr)

    if export_sqlite(sqlite_path):
        print(f"[sqlite] exported to {EXPORT_ROOT / 'sqlite'}")
    if export_duckdb(duck_path):
        print(f"[duckdb] exported to {EXPORT_ROOT / 'duckdb'}")

    print(f"\nDone. Root: {EXPORT_ROOT}")
    print(f"Max rows per object: {MAX_ROWS} (set DATABASE_EXPORT_MAX_ROWS to change).")
    return 0 if (ok_pg or ok_m or True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
