"""
Load Yelp DAB slices into PostgreSQL so SQL tools can answer benchmarks alongside MongoDB/DuckDB.

Expects:
  - MongoDB `yelp_db.business` (from mongo-seed / bson dump)
  - DuckDB file at DUCKDB_PATH (review, user tables)

Adds derived columns (state, credit card / WiFi flags, category tags) using the same
logic as `scripts/reconcile_yelp_ground_truth.py` so templates match `ground_truth.csv`.

Environment:
  POSTGRES_DSN — e.g. postgresql://postgres:postgres@localhost:5432/oracleforge
  MONGODB_URI — e.g. mongodb://localhost:27017
  MONGODB_DATABASE — default yelp_db
  DUCKDB_PATH — path to yelp_user.db (repo-relative or absolute)
  REPO_ROOT — optional override; defaults to parent of scripts/
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import asyncpg
import duckdb
from bson import decode_all
from pymongo import MongoClient


def _repo_root() -> Path:
    env = os.getenv("REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def _import_yelp_helpers(repo: Path) -> Tuple[Any, Any]:
    scripts = str(repo / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from yelp_dab_categories import categories_for_business, categories_from_featuring_block
    from yelp_dab_derived import accepts_credit_cards, has_wifi, state_from_description

    return (
        (categories_for_business, categories_from_featuring_block),
        (accepts_credit_cards, has_wifi, state_from_description),
    )


def _business_row_from_doc(doc: dict[str, Any], helpers: Tuple[Any, Any]) -> Tuple[Any, ...]:
    (categories_for_business, categories_from_featuring_block) = helpers[0]
    (accepts_credit_cards, has_wifi, state_from_description) = helpers[1]
    desc = str(doc.get("description") or "")
    attrs = doc.get("attributes")
    ft = categories_from_featuring_block(desc)
    primary = "|".join(ft) if ft else ""
    return (
        str(doc.get("business_id", "")),
        str(doc.get("name", "") or ""),
        desc,
        int(doc.get("review_count") or 0),
        int(doc.get("is_open") or 0),
        str(doc.get("attributes", "") or ""),
        str(doc.get("hours", "") or ""),
        state_from_description(desc) or "",
        bool(accepts_credit_cards(attrs)),
        bool(has_wifi(attrs)),
        primary,
    )


def _category_rows_from_doc(doc: dict[str, Any], helpers: Tuple[Any, Any]) -> List[Tuple[str, str]]:
    (categories_for_business, _feat) = helpers[0]
    bid = str(doc.get("business_id", ""))
    return [(bid, c) for c in categories_for_business(doc)]


async def _ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        DROP TABLE IF EXISTS review CASCADE;
        DROP TABLE IF EXISTS business_category CASCADE;
        DROP TABLE IF EXISTS "user" CASCADE;
        DROP TABLE IF EXISTS business CASCADE;
        """
    )
    await conn.execute(
        """
        CREATE TABLE business (
            business_id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            review_count INT,
            is_open INT,
            attributes TEXT,
            hours TEXT,
            state_code TEXT,
            accepts_credit_cards BOOLEAN,
            has_wifi BOOLEAN,
            primary_categories TEXT
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE business_category (
            business_id TEXT NOT NULL REFERENCES business(business_id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            PRIMARY KEY (business_id, category)
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE review (
            review_id TEXT PRIMARY KEY,
            user_id TEXT,
            business_id TEXT,
            stars INT,
            date TEXT,
            text TEXT
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE "user" (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            review_count INT,
            yelping_since TEXT,
            useful INT,
            funny INT,
            cool INT,
            elite TEXT
        );
        """
    )


def _load_business_docs_from_bson(path: Path) -> List[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"business bson not found: {path}")
    return decode_all(path.read_bytes())


def _load_business_docs_from_mongo(mongo_uri: str, db_name: str) -> List[dict[str, Any]]:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return list(client[db_name]["business"].find())


def _load_business_docs(repo: Path, mongo_uri: str, db_name: str, bson_path: Path | None) -> List[dict[str, Any]]:
    use_mongo = os.getenv("YELP_SEED_USE_MONGO", "").lower() in {"1", "true", "yes"}
    if use_mongo:
        return _load_business_docs_from_mongo(mongo_uri, db_name)
    path = bson_path or (repo / "DataAgentBench/query_yelp/query_dataset/yelp_business/yelp_db/business.bson")
    return _load_business_docs_from_bson(path)


def _load_review_rows(duck_path: Path) -> List[Sequence[Any]]:
    con = duckdb.connect(str(duck_path))
    data = con.execute(
        """
        SELECT review_id, user_id, business_ref, CAST(rating AS INT), date, text
        FROM review
        """
    ).fetchall()
    return [tuple(r) for r in data]


def _load_user_rows(duck_path: Path) -> List[Sequence[Any]]:
    con = duckdb.connect(str(duck_path))
    data = con.execute(
        """
        SELECT user_id, name, CAST(review_count AS INT), yelping_since,
               CAST(useful AS INT), CAST(funny AS INT), CAST(cool AS INT), elite
        FROM "user"
        """
    ).fetchall()
    return [tuple(r) for r in data]


async def _copy_business(conn: asyncpg.Connection, rows: List[Sequence[Any]]) -> None:
    await conn.copy_records_to_table(
        "business",
        records=rows,
        columns=[
            "business_id",
            "name",
            "description",
            "review_count",
            "is_open",
            "attributes",
            "hours",
            "state_code",
            "accepts_credit_cards",
            "has_wifi",
            "primary_categories",
        ],
    )


async def _copy_business_category(conn: asyncpg.Connection, rows: List[Tuple[str, str]]) -> None:
    if not rows:
        return
    await conn.copy_records_to_table(
        "business_category",
        records=rows,
        columns=["business_id", "category"],
    )


async def _copy_review(conn: asyncpg.Connection, rows: List[Sequence[Any]]) -> None:
    await conn.copy_records_to_table(
        "review",
        records=rows,
        columns=["review_id", "user_id", "business_id", "stars", "date", "text"],
    )


async def _copy_user(conn: asyncpg.Connection, rows: List[Sequence[Any]]) -> None:
    await conn.copy_records_to_table(
        "user",
        records=rows,
        columns=["user_id", "name", "review_count", "yelping_since", "useful", "funny", "cool", "elite"],
    )


async def main_async() -> None:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/oracleforge").strip()
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
    mongo_db = os.getenv("MONGODB_DATABASE", "yelp_db").strip()
    repo = _repo_root()
    helpers = _import_yelp_helpers(repo)
    duck = Path(os.getenv("DUCKDB_PATH", str(repo / "DataAgentBench/query_yelp/query_dataset/yelp_user.db"))).resolve()
    if not duck.exists():
        raise FileNotFoundError(f"DuckDB file not found: {duck}")

    print(f"Seeding PostgreSQL via {dsn.split('@')[-1]}")
    use_mongo = os.getenv("YELP_SEED_USE_MONGO", "").lower() in {"1", "true", "yes"}
    if use_mongo:
        print(f"Business rows source: MongoDB {mongo_uri} db={mongo_db}")
    else:
        print("Business rows source: local BSON (YELP_BUSINESS_BSON or default path)")
    print(f"DuckDB: {duck}")

    bson_override = os.getenv("YELP_BUSINESS_BSON", "").strip()
    bson_path = Path(bson_override).resolve() if bson_override else None
    business_docs = _load_business_docs(repo, mongo_uri, mongo_db, bson_path)
    business_rows = [_business_row_from_doc(doc, helpers) for doc in business_docs]
    category_rows: List[Tuple[str, str]] = []
    for doc in business_docs:
        category_rows.extend(_category_rows_from_doc(doc, helpers))
    review_rows = _load_review_rows(duck)
    user_rows = _load_user_rows(duck)
    print(
        f"Loaded business={len(business_rows)} category_rows={len(category_rows)} "
        f"review={len(review_rows)} user={len(user_rows)} rows"
    )

    conn = await asyncpg.connect(dsn)
    try:
        await _ensure_schema(conn)
        await _copy_business(conn, business_rows)
        await _copy_business_category(conn, category_rows)
        await _copy_review(conn, review_rows)
        await _copy_user(conn, user_rows)
    finally:
        await conn.close()

    print("PostgreSQL Yelp seed completed.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
