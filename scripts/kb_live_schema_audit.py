#!/usr/bin/env python3
"""Introspect live DBs and emit JSON for KB comparison (run from repo root)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAB = REPO / "DataAgentBench"
PG = "oracle-forge-mcp-postgres-1"
MG = "oracle-forge-mcp-mongo-1"


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        return f"ERROR: {p.stderr}"
    return p.stdout.strip()


def pg_tables(db: str) -> list[str]:
    out = _run(
        [
            "docker",
            "exec",
            PG,
            "psql",
            "-U",
            "postgres",
            "-d",
            db,
            "-At",
            "-c",
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
            "AND table_type='BASE TABLE' ORDER BY 1",
        ]
    )
    if out.startswith("ERROR"):
        return []
    return [x.strip() for x in out.splitlines() if x.strip()]


def pg_columns(db: str, table: str) -> list[str]:
    ident = f'"{table}"' if table.lower() == "user" or not table.replace("_", "").isalnum() else table
    out = _run(
        [
            "docker",
            "exec",
            PG,
            "psql",
            "-U",
            "postgres",
            "-d",
            db,
            "-At",
            "-c",
            f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
            f"AND table_name = '{table}' ORDER BY ordinal_position",
        ]
    )
    return [x.strip() for x in out.splitlines() if x.strip()]


def pg_sample(db: str, table: str, n: int = 2) -> list[dict]:
    import csv
    import io

    ident = f'"{table}"' if table.lower() == "user" else table
    raw = _run(
        [
            "docker",
            "exec",
            PG,
            "psql",
            "-U",
            "postgres",
            "-d",
            db,
            "-At",
            "-F",
            chr(9),
            "-c",
            f"COPY (SELECT * FROM {ident} LIMIT {n}) TO STDOUT WITH CSV HEADER",
        ]
    )
    if raw.startswith("ERROR") or not raw:
        return []
    r = csv.DictReader(io.StringIO(raw), delimiter="\t")
    return list(r)


def mongo_collections(db: str) -> list[str]:
    out = _run(
        [
            "docker",
            "exec",
            MG,
            "mongosh",
            db,
            "--quiet",
            "--eval",
            "db.getCollectionNames().filter(c => !c.startsWith('system.')).sort().join('\\n')",
        ]
    )
    return [x.strip() for x in out.splitlines() if x.strip()]


def mongo_sample(db: str, coll: str, n: int = 2) -> list[dict]:
    js = f"JSON.stringify(db.getCollection('{coll}').find().limit({n}).toArray())"
    out = _run(["docker", "exec", MG, "mongosh", db, "--quiet", "--eval", js])
    if out.startswith("ERROR"):
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return [{"_raw": out[:500]}]


def sqlite_info(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    con = sqlite3.connect(str(path))
    cur = con.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1"
    )
    tables = [r[0] for r in cur.fetchall()]
    cols: dict[str, list[str]] = {}
    for t in tables:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols[t] = [r[1] for r in cur.fetchall()]
    con.close()
    return tables, cols


def duck_tables(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    tabs = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1"
        ).fetchall()
    ]
    cols = {}
    for t in tabs:
        ident = f'"{t}"' if t.lower() == "user" else t
        rows = con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}' ORDER BY ordinal_position").fetchall()
        cols[t] = [r[0] for r in rows]
    con.close()
    return tabs, cols


def parse_db_configs() -> list[tuple[str, str, Path]]:
    """(dataset, kind, path) for sqlite and duckdb."""
    out: list[tuple[str, str, Path]] = []
    for cfg in sorted(DAB.glob("query_*/db_config.yaml")):
        ds = cfg.parent.name
        cur = None
        for line in cfg.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("db_type:"):
                cur = s.split(":", 1)[1].strip().split()[0].lower()
            elif s.startswith("db_path:") and cur in ("sqlite", "duckdb"):
                rel = s.split(":", 1)[1].strip().split()[0]
                out.append((ds, cur, (cfg.parent / rel).resolve()))
    return out


def main() -> None:
    report: dict = {"postgres": {}, "mongodb": {}, "sqlite_duckdb": {}}

    for db in [
        "oracleforge",
        "bookreview_db",
        "googlelocal_db",
        "crm_support",
        "pancancer_clinical",
        "patent_CPCDefinition",
    ]:
        tbls = pg_tables(db)
        report["postgres"][db] = {}
        for t in tbls:
            report["postgres"][db][t] = {
                "columns": pg_columns(db, t),
                "sample_rows": pg_sample(db, t),
            }

    for db in ["yelp_db", "articles_db"]:
        colls = mongo_collections(db)
        report["mongodb"][db] = {}
        for c in colls:
            docs = mongo_sample(db, c)
            # flatten keys only for schema-ish view
            keys = sorted({k for d in docs for k in d.keys()}) if docs else []
            report["mongodb"][db][c] = {"top_level_keys": keys, "sample_docs": docs}

    for ds, kind, p in parse_db_configs():
        key = f"{ds}:{kind}:{p.name}"
        if not p.is_file():
            report["sqlite_duckdb"][key] = {"error": "missing file", "path": str(p)}
            continue
        try:
            if kind == "sqlite":
                tables, colmap = sqlite_info(p)
                samples = {}
                con = sqlite3.connect(str(p))
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                for t in tables:
                    cur.execute(f'SELECT * FROM "{t}"' if not t.isidentifier() else f"SELECT * FROM {t} LIMIT 2")
                    samples[t] = [dict(row) for row in cur.fetchall()]
                con.close()
                report["sqlite_duckdb"][key] = {"tables": tables, "columns": colmap, "samples": samples}
            else:
                tables, colmap = duck_tables(p)
                import duckdb as ddb

                con = ddb.connect(str(p), read_only=True)
                samples = {}
                for t in tables:
                    ident = f'"{t}"' if t.lower() == "user" else t
                    rows = con.execute(f"SELECT * FROM {ident} LIMIT 2").fetchall()
                    cnames = colmap[t]
                    samples[t] = [dict(zip(cnames, r)) for r in rows]
                con.close()
                report["sqlite_duckdb"][key] = {"tables": tables, "columns": colmap, "samples": samples}
        except Exception as exc:
            report["sqlite_duckdb"][key] = {"error": str(exc), "path": str(p)}

    out_path = REPO / "eval" / "kb_live_audit_snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "summary": {k: len(v) for k, v in report.items()}}, indent=2))


if __name__ == "__main__":
    main()
