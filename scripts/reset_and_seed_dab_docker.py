#!/usr/bin/env python3
"""
Reset PostgreSQL + MongoDB (Docker) and load DataAgentBench server-side data.

- Postgres: DROP/CREATE each DAB database, apply pg_dump-style SQL files, then seed Yelp into `oracleforge`.
- Mongo: `mongorestore --drop` for Yelp (`yelp_db`) and AG News (`articles_db`).

Requires Docker with containers `oracle-forge-mcp-postgres-1` and `oracle-forge-mcp-mongo-1`
on network `oracle-forge-mcp_default` (default from mcp/docker-compose.yml).

Usage (repo root):
  python scripts/reset_and_seed_dab_docker.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parents[1]

PG_CONTAINER = os.getenv("DAB_PG_CONTAINER", "oracle-forge-mcp-postgres-1")
MONGO_CONTAINER = os.getenv("DAB_MONGO_CONTAINER", "oracle-forge-mcp-mongo-1")
DOCKER_NETWORK = os.getenv("DAB_DOCKER_NETWORK", "oracle-forge-mcp_default")

# Databases to recreate (Postgres)
PG_SQL_LOADS: List[Tuple[str, Path]] = [
    ("bookreview_db", REPO / "DataAgentBench/query_bookreview/query_dataset/books_info.sql"),
    ("googlelocal_db", REPO / "DataAgentBench/query_googlelocal/query_dataset/business_description.sql"),
    ("crm_support", REPO / "DataAgentBench/query_crmarenapro/query_dataset/support.sql"),
    ("pancancer_clinical", REPO / "DataAgentBench/query_PANCANCER_ATLAS/query_dataset/pancancer_clinical.sql"),
    ("patent_CPCDefinition", REPO / "DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"),
]

ORACLEFORGE = "oracleforge"


def _require_docker() -> None:
    proc = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        timeout=60,
        text=True,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip() or "unknown error"
        raise RuntimeError(
            "Docker is not reachable (is Docker Desktop running?).\n" + msg
        )


def _run(cmd: List[str], *, stdin: bytes | None = None, input_path: Path | None = None) -> None:
    if input_path is not None:
        with input_path.open("rb") as fh:
            proc = subprocess.run(cmd, stdin=fh, capture_output=True)
    else:
        proc = subprocess.run(cmd, input=stdin, capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        out = proc.stdout.decode("utf-8", errors="replace")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{err}\n{out}")


def _docker_exec_psql(sql: str) -> None:
    _run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1"],
        stdin=sql.encode("utf-8"),
    )


def _psql_file(db: str, sql_path: Path) -> None:
    if not sql_path.is_file():
        raise FileNotFoundError(f"Missing SQL file: {sql_path}")
    _run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1"],
        input_path=sql_path,
    )


def _drop_postgres_databases() -> None:
    names = [ORACLEFORGE] + [d for d, _ in PG_SQL_LOADS]
    for name in names:
        _docker_exec_psql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}' AND pid <> pg_backend_pid();\n"
            f"DROP DATABASE IF EXISTS \"{name}\" WITH (FORCE);\n"
        )


def _create_postgres_databases() -> None:
    names = [ORACLEFORGE] + [d for d, _ in PG_SQL_LOADS]
    for name in names:
        _docker_exec_psql(f'CREATE DATABASE "{name}" OWNER postgres;\n')


def _mongo_drop(db_name: str) -> None:
    js = f"db.getSiblingDB('{db_name}').dropDatabase()"
    _run(
        ["docker", "exec", MONGO_CONTAINER, "mongosh", "--quiet", "--eval", js],
    )


def _mongorestore(dump_subdir: str) -> None:
    """Run mongorestore from a mongo client container with repo mounted at /workspace."""
    in_container = f"/workspace/{dump_subdir.replace(chr(92), '/')}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        DOCKER_NETWORK,
        "-v",
        f"{REPO}:/workspace:ro",
        "mongo:7",
        "mongorestore",
        f"--uri=mongodb://{MONGO_CONTAINER}:27017",
        "--drop",
        in_container,
    ]
    _run(cmd)


def _seed_yelp_postgres_docker() -> None:
    """Run seed_yelp_postgres.py inside python container on the compose network."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        DOCKER_NETWORK,
        "-v",
        f"{REPO}:/workspace",
        "-w",
        "/workspace",
        "-e",
        "POSTGRES_DSN=postgresql://postgres:postgres@" + PG_CONTAINER + ":5432/oracleforge",
        "-e",
        "MONGODB_URI=mongodb://" + MONGO_CONTAINER + ":27017",
        "-e",
        "MONGODB_DATABASE=yelp_db",
        "-e",
        "YELP_SEED_USE_MONGO=true",
        "-e",
        "DUCKDB_PATH=/workspace/DataAgentBench/query_yelp/query_dataset/yelp_user.db",
        "python:3.12-slim",
        "bash",
        "-lc",
        "pip install --no-cache-dir -q 'asyncpg>=0.29.0' 'pymongo>=4.6.0' 'duckdb>=0.10.0' && "
        "python scripts/seed_yelp_postgres.py",
    ]
    _run(cmd)


def main() -> int:
    _require_docker()

    print(f"Repo: {REPO}")
    print(f"Postgres container: {PG_CONTAINER}")
    print(f"Mongo container: {MONGO_CONTAINER}")

    for _, p in PG_SQL_LOADS:
        if not p.is_file():
            print(f"ERROR: required file missing: {p}", file=sys.stderr)
            return 1

    yelp_dump = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_business"
    agnews_dump = REPO / "DataAgentBench/query_agnews/query_dataset/agnews_articles"
    duckdb_yelp = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_user.db"
    for label, path in ("Yelp BSON dump", yelp_dump), ("AG News BSON dump", agnews_dump), ("Yelp DuckDB", duckdb_yelp):
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            return 1

    print("--- Dropping MongoDB databases (yelp_db, articles_db) ---")
    _mongo_drop("yelp_db")
    _mongo_drop("articles_db")

    print("--- Dropping PostgreSQL application databases ---")
    _drop_postgres_databases()

    print("--- Creating empty PostgreSQL databases ---")
    _create_postgres_databases()

    print("--- Loading pg_dump SQL into non-Yelp databases ---")
    for db, sql_path in PG_SQL_LOADS:
        print(f"  {db} <= {sql_path.name}")
        _psql_file(db, sql_path)

    print("--- mongorestore Yelp (yelp_db) ---")
    _mongorestore("DataAgentBench/query_yelp/query_dataset/yelp_business")

    print("--- mongorestore AG News (articles_db) ---")
    _mongorestore("DataAgentBench/query_agnews/query_dataset/agnews_articles")

    print("--- Seeding oracleforge (Yelp mirror via seed_yelp_postgres.py) ---")
    _seed_yelp_postgres_docker()

    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
