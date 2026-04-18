# DuckDB Schemas for DAB Datasets

Default Oracle Forge mounts **`DataAgentBench/query_yelp/query_dataset/yelp_user.db`** (`DUCKDB_PATH`). It contains **only** the Yelp slice in the first section below.

Sections marked **Reference (illustrative)** describe shapes used in examples or **other** DAB files — they are **not** guaranteed to exist in `yelp_user.db` or in every benchmark file. Always introspect the active file (`information_schema.tables`, `PRAGMA`) when in doubt.

---

## Yelp dataset (`yelp_user.db`) — verified

### Table: `review`

- review_id (VARCHAR)
- user_id (VARCHAR)
- business_ref (VARCHAR) — aligns with Postgres `review.business_id` / Mongo `business.business_id` after normalizing `businessid_*` ↔ `businessref_*` style ids
- rating (BIGINT) — 1–5; same semantics as Postgres `review.stars`
- useful (BIGINT)
- funny (BIGINT)
- cool (BIGINT)
- text (VARCHAR)
- date (VARCHAR)

### Table: `tip`

- user_id (VARCHAR)
- business_ref (VARCHAR)
- text (VARCHAR)
- date (VARCHAR)
- compliment_count (BIGINT)

### Table: `user`

- user_id (VARCHAR)
- name (VARCHAR)
- review_count (BIGINT)
- yelping_since (VARCHAR)
- useful (BIGINT)
- funny (BIGINT)
- cool (BIGINT)
- elite (VARCHAR)

There are **no** `business` or `checkin` **tables** in this DuckDB file. Business-level fields live in **PostgreSQL `business`** and **MongoDB `business`**; check-in events for Mongo are in **`checkin`** (see `mongodb_schemas.md`).

### Rating and aggregation note

- Per-review scores: use **`review.rating`** (DuckDB) and **`review.stars`** (Postgres). **`business` in Postgres has no `stars` column** in the seeded schema.
- Do not assume **embedded reviews** on Mongo `business` in the default dump; aggregate from SQL/DuckDB review tables when the question is about star ratings.

---

## PANCANCER_ATLAS — `pancancer_molecular.db` (verified DataAgentBench)

**Path:** `DataAgentBench/query_PANCANCER_ATLAS/query_dataset/pancancer_molecular.db`

Pair with PostgreSQL **`pancancer_clinical.clinical_info`** (`patient_id` and TCGA clinical fields). Join keys use **TCGA sample / participant barcodes** — see `join_key_mappings.md` (`resolve_tcga_id`).

### Table: `Mutation_Data`

- ParticipantBarcode (VARCHAR) — e.g. `TCGA-AX-A3G8`
- Tumor_SampleBarcode, Tumor_AliquotBarcode, Normal_SampleBarcode, Normal_AliquotBarcode (VARCHAR)
- Normal_SampleTypeLetterCode (VARCHAR)
- Hugo_Symbol (VARCHAR)
- HGVSp_Short, HGVSc (VARCHAR)
- Variant_Classification (VARCHAR)
- CENTERS, FILTER (VARCHAR)

### Table: `RNASeq_Expression`

- ParticipantBarcode (VARCHAR)
- SampleBarcode, AliquotBarcode (VARCHAR)
- SampleTypeLetterCode, SampleType (VARCHAR)
- Symbol (VARCHAR)
- Entrez (BIGINT)
- normalized_count (DOUBLE)

**Deprecated KB sketch:** an older one-line `gene_expression` example with `patient_id` / `gene_symbol` is **not** this file’s layout — use **`Mutation_Data`** and **`RNASeq_Expression`** as above.

---

## Stock benchmarks — DuckDB identifier quoting

**Paths:** e.g. `query_stockmarket/query_dataset/stocktrade_query.db`, `query_stockindex/query_dataset/indextrade_query.db`.

Table names may include **`#`** or other special characters. Quote identifiers: e.g. `SELECT * FROM "CARR#"` — not `FROM CARR#`.

---

## Reference (illustrative): Analytics cube — not in `yelp_user.db`

### Table: `sales_fact`

- sale_id (BIGINT, PK)
- customer_id (INTEGER)
- product_id (INTEGER)
- sale_date (DATE)
- amount (DECIMAL(10,2))
- quantity (INTEGER)

### Table: `time_dimension`

- date_key (DATE, PK)
- year (INTEGER)
- quarter (INTEGER)
- month (INTEGER)
- fiscal_year (INTEGER)
- fiscal_quarter (INTEGER)

---

## Reference (illustrative): crmarenapro file-backed DuckDB

**Path:** `DataAgentBench/query_crmarenapro/query_dataset/sales_pipeline.duckdb` (and **`activities.duckdb`** — introspect).

Older docs sometimes showed hypothetical **`churn_predictions`** / **`loyalty`** tables. The **loaded** DAB DuckDB files may differ; **PostgreSQL `crm_support`** is the authoritative relational source for support-case objects when that seed is applied (`Case`, `emailmessage`, … — see `postgresql_schemas.md`). Introspect the active `.duckdb` file for exact table/column names.

---

## Reference (illustrative): GitHub dataset

**Path:** `DataAgentBench/query_GITHUB_REPOS/query_dataset/repo_artifacts.db`

### Table: `contributors` (typical)

- id (BIGINT, PK)
- repo_id (BIGINT)
- contributor_login (TEXT)
- commits (INTEGER)
- additions (INTEGER)
- deletions (INTEGER)

### Table: `repositories` (typical)

- repo_id (BIGINT, PK)
- name (TEXT)
- language (TEXT)
- stars (INTEGER)
- forks (INTEGER)
- created_at (DATE)

Introspect — names may vary slightly by export.

---

## Important for DAB

DuckDB is used for analytical queries (GROUP BY, window functions). **Fiscal calendar** notes for telecom-style examples: see `kb/domain/domain_terms/business_glossary.md`.

## DAB-style SQL examples (reference schemas only)

Examples below assume **`sales_fact`** / **`time_dimension`** exist in the active DuckDB file — they do **not** apply to `yelp_user.db` alone.

```sql
SELECT
    customer_segment,
    fiscal_quarter,
    COUNT(DISTINCT customer_id) AS customers,
    SUM(amount) AS revenue
FROM sales_fact
JOIN time_dimension ON sales_fact.sale_date = time_dimension.date_key
WHERE time_dimension.fiscal_quarter = 3
GROUP BY customer_segment, fiscal_quarter;
```

---

## Injection tests

Q: Which tables exist in the default `yelp_user.db`?

A: `review`, `tip`, and `user`.

Q: Which DuckDB tables hold PANCANCER molecular data in the shipped file?

A: **`Mutation_Data`** and **`RNASeq_Expression`** in `pancancer_molecular.db`.

Q: Why might `SELECT * FROM CARR#` fail?

A: **`#` requires a quoted identifier** (e.g. `"CARR#"`); the bare token is a syntax error.
