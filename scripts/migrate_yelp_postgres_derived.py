"""
Add Yelp DAB derived columns + business_category to an existing oracleforge DB.

Use when Postgres was seeded before `state_code` / `business_category` existed.
Does not DROP data in review/user — only ALTER + backfill from BSON/Mongo.

  python scripts/migrate_yelp_postgres_derived.py

Env: POSTGRES_DSN, REPO_ROOT, YELP_SEED_USE_MONGO, MONGODB_*, DUCKDB_PATH, YELP_BUSINESS_BSON
(same as seed_yelp_postgres.py)
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

import asyncpg

# Reuse seed helpers
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo_root() -> Path:
    env = os.getenv("REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return ROOT


async def _column_exists(conn: asyncpg.Connection, table: str, column: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2
        """,
        table,
        column,
    )
    return row is not None


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return row is not None


async def _ensure_derived_ddl(conn: asyncpg.Connection) -> None:
    if not await _table_exists(conn, "business"):
        raise RuntimeError(
            "Table `business` not found. Run `python scripts/seed_yelp_postgres.py` first."
        )
    alters = [
        ("state_code", "TEXT"),
        ("accepts_credit_cards", "BOOLEAN"),
        ("has_wifi", "BOOLEAN"),
        ("primary_categories", "TEXT"),
    ]
    for col, typ in alters:
        if not await _column_exists(conn, "business", col):
            await conn.execute(f"ALTER TABLE business ADD COLUMN {col} {typ}")
            print(f"Added column business.{col}")

    if not await _table_exists(conn, "business_category"):
        await conn.execute(
            """
            CREATE TABLE business_category (
                business_id TEXT NOT NULL REFERENCES business(business_id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                PRIMARY KEY (business_id, category)
            );
            """
        )
        print("Created table business_category")


async def _backfill(conn: asyncpg.Connection) -> None:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from seed_yelp_postgres import (  # type: ignore
        _category_rows_from_doc,
        _business_row_from_doc,
        _import_yelp_helpers,
        _load_business_docs,
    )

    repo = _repo_root()
    helpers = _import_yelp_helpers(repo)
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
    mongo_db = os.getenv("MONGODB_DATABASE", "yelp_db").strip()
    bson_override = os.getenv("YELP_BUSINESS_BSON", "").strip()
    bson_path = Path(bson_override).resolve() if bson_override else None
    docs = _load_business_docs(repo, mongo_uri, mongo_db, bson_path)
    print(f"Backfilling derived fields for {len(docs)} businesses...")

    await conn.execute("DELETE FROM business_category")

    for doc in docs:
        row = _business_row_from_doc(doc, helpers)
        # row: id, name, desc, rc, open, attrs, hours, state, cc, wifi, primary_cats
        await conn.execute(
            """
            UPDATE business SET
              state_code = $2,
              accepts_credit_cards = $3,
              has_wifi = $4,
              primary_categories = $5
            WHERE business_id = $1
            """,
            row[0],
            row[7] or None,
            row[8],
            row[9],
            row[10] or None,
        )

    cat_rows: List[Tuple[str, str]] = []
    for doc in docs:
        cat_rows.extend(_category_rows_from_doc(doc, helpers))
    if cat_rows:
        await conn.copy_records_to_table(
            "business_category",
            records=cat_rows,
            columns=["business_id", "category"],
        )
    print(f"Inserted {len(cat_rows)} business_category rows.")


async def main_async() -> None:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/oracleforge").strip()
    print(f"Migrating {dsn.split('@')[-1]}")
    conn = await asyncpg.connect(dsn)
    try:
        await _ensure_derived_ddl(conn)
        await _backfill(conn)
    finally:
        await conn.close()
    print("migrate_yelp_postgres_derived completed.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
