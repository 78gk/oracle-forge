# MongoDB Schemas for DAB Datasets

Default Oracle Forge loads **`yelp_db`** from `DataAgentBench/query_yelp/query_dataset/yelp_business` via `mongorestore` (`mcp/docker-compose.yml` profile `seed`). That dump contains **`business`** and **`checkin`** only—there is **no** `user` collection and **no** embedded `reviews` arrays on `business` in this deployment.

## Yelp Dataset (loaded in Docker)

### Collection: business

Documents are **flat** (attributes on the document root). They do **not** embed a `reviews` array; review text and stars are sourced from **PostgreSQL `review`**, **DuckDB `review`**, and the seeded Postgres/`user` tables as appropriate.

Typical fields (subset may vary per document):

- `_id` (ObjectId)
- `business_id` (string)
- `name` (string)
- `description` (string)
- `review_count` (number)
- `is_open` (number or bool)
- `attributes` (object or serialized)
- `hours` (object or serialized)

### Collection: checkin

- `_id` (ObjectId)
- `business_id` (string)
- `date` (string) — in the restored data this is often a **single string** containing **comma-separated** check-in timestamps (not an array of sub-documents). Parse or split in application code if you need per-event counts.

There is **no** separate Mongo collection for per-review rows in this dump; do not assume `db.reviews` or embedded review arrays.

---

## AG News (`articles_db`) — loaded from `query_agnews/query_dataset/agnews_articles`

When `mongorestore` is run for DataAgentBench AG News, database **`articles_db`** contains:

### Collection: `articles`

- `_id` (ObjectId)
- `article_id` (number)
- `title` (string)
- `description` (string) — article body/snippet text

Pair with SQLite **`metadata.db`** (`article_metadata`, `authors`) under the same `query_agnews/query_dataset/` path — see `sqlite_schemas.md`.

---

## Reference: Telecom / healthcare (not in default `yelp_db`)

Illustrative shapes for cross-database join examples. **Not** loaded by the default Yelp `mongorestore`.

### Collection: subscribers (reference)

```json
{
  "customer_id": "CUST-1234567",
  "plan_type": "postpaid",
  "monthly_revenue": 89.99
}
```

### Collection: support tickets (reference)

```json
{
  "ticket_id": "TKT-12345678",
  "customer_id": "CUST-1234567",
  "issue_description": "Frustrated with service",
  "resolution_time_hours": 24
}
```

### Collection: claims (reference)

```json
{
  "claim_id": "CLM-98765",
  "patient_id": "PT-987654321",
  "provider_npi": "NPI-1234567890",
  "clinical_notes": "Patient prescribed Lisinopril 10mg daily",
  "status": "paid"
}
```

## Critical join notes

- For **default Yelp data**, join **business** by `business_id` to Postgres `business.business_id` / DuckDB `review.business_ref` / Postgres `review.business_id` using the documented key mapping.
- For **reference** telecom/healthcare docs: MongoDB IDs are often **strings** with prefixes; PostgreSQL may use INTs — transform before joining (`resolve_join_key`).

## Injection tests

Q: Which collections exist in the default seeded `yelp_db`?

A: `business` and `checkin` (no `user` collection in the default dump).

Q: What is in MongoDB `articles_db` for AG News?

A: Collection **`articles`** with `article_id`, `title`, `description` (plus `_id`).
