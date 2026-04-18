# SQLite Schemas for DAB Datasets

The **default MCP toolbox** (`mcp/docker-compose.yml`) mounts:

`DataAgentBench/query_bookreview/query_dataset/review_query.db`

(`SQLITE_PATH` in `.env`; relative path `eval/datasets.json` → `bookreview.sqlite_path`.)

Other benchmarks use **different files** on disk (paths in each `query_*/db_config.yaml`). Always use the path for the active dataset — e.g. `query_googlelocal/query_dataset/review_query.db` is **not** the same file as the bookreview path even when the filename matches.

---

## Book Review dataset (default MCP mount)

**Path:** `DataAgentBench/query_bookreview/query_dataset/review_query.db`

### Table: `review`

- rating (INTEGER)
- title (TEXT)
- text (TEXT)
- review_time (TEXT)
- helpful_vote (INTEGER)
- verified_purchase (INTEGER)
- purchase_id (TEXT)

This is **book-review** content (Amazon-style), not generic transaction logs.

---

## AG News — `metadata.db`

**Path:** `DataAgentBench/query_agnews/query_dataset/metadata.db`

Used together with MongoDB **`articles_db`** (`articles` collection).

### Table: `article_metadata`

- article_id — joins to Mongo `articles.article_id`
- author_id — joins to **`authors`**.author_id
- region (TEXT)
- publication_date (TEXT)

### Table: `authors`

- author_id (TEXT or INTEGER per dump — match with `article_metadata.author_id`)
- name (TEXT)

---

## Google Local — `review_query.db`

**Path:** `DataAgentBench/query_googlelocal/query_dataset/review_query.db` (distinct from bookreview’s file).

Introspect with `PRAGMA table_info` when this path is active; schema parallels local-review style fields for the googlelocal benchmark.

---

## Stock market / index benchmarks — identifier quoting

**Paths:** e.g. `query_stockmarket/query_dataset/stockinfo_query.db`, `query_stockindex/query_dataset/indexInfo_query.db`.

Some dumps use **non-standard table names** (including **`#`**). In SQL you must quote identifiers, e.g. `"CARR#"` in DuckDB/SQLite — a bare `CARR#` token is invalid syntax.

---

## Other dataset paths (`eval/datasets.json`)

When present on disk, additional SQLite files include crmarenapro (`core_crm.db`, `products_orders.db`, `territory.db`), DEPS_DEV (`package_query.db`), GITHUB (`repo_metadata.db`), music (`tracks.db`), PATENTS (`patent_publication.db` — large), stock benchmarks, etc. Introspect with `PRAGMA table_info(<table>)` for the file in use.

Legacy note: some docs mention **`agnews_mongo.db`** as an alternate filename; the shipped DAB layout uses **`metadata.db`** + Mongo **`articles_db`** as documented above.

---

## Note for joins

Integer IDs in SQLite stay integer; MongoDB telecom-style IDs often need `f"CUST-{customer_id}"` when joining **reference** scenarios (see `kb/domain/joins/join_key_mappings.md`).

---

## Injection tests

Q: What tables does the default `review_query.db` (bookreview path) expose?

A: A single table, `review`, with columns `rating`, `title`, `text`, `review_time`, `helpful_vote`, `verified_purchase`, `purchase_id`.

Q: What SQLite tables back AG News metadata?

A: **`article_metadata`** and **`authors`** in `query_agnews/query_dataset/metadata.db`.
