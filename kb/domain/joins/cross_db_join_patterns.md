# Cross-Database Join Patterns

Patterns below are **procedural**. Table names must match the **active** database (see `postgresql_schemas.md`, `mongodb_schemas.md`). Telecom/healthcare examples use **reference** schemas; DataAgentBench **`crm_support`** uses **`"Case"`**, **`emailmessage`**, etc., not generic `transactions` + `support_tickets` unless your seed adds them.

---

## Pattern 1: PostgreSQL to MongoDB (one-to-many)

**Scenario:** Join customer facts (PostgreSQL) with related documents (MongoDB).

**Steps:**

1. **Start from PostgreSQL** when it holds stable identifiers (see eval notes — do not reverse order blindly).
2. If Mongo uses prefixed strings (e.g. telecom `CUST-{id}`), transform: `f"CUST-{customer_id}"`.
3. Query MongoDB with transformed IDs.
4. Merge on the transformed key.

**Example MongoDB aggregation (illustrative collection names):**

```javascript
db.support_tickets.aggregate([
  { $match: { customer_id: { $in: transformed_ids } } },
  { $group: { _id: "$customer_id", ticket_count: { $sum: 1 } } }
])
```

For **seeded Yelp**, per-review data is **not** in Mongo — use Postgres/DuckDB `review` (see `join_key_mappings.md`).

---

## Pattern 2: MongoDB to PostgreSQL (string to INT)

**Scenario:** MongoDB stores `"CUST-12345"`; PostgreSQL stores `12345`.

**Steps:**

1. Read string ids from MongoDB.
2. Extract the numeric part (e.g. strip `CUST-`).
3. Query PostgreSQL with integers (or cast consistently).
4. Merge results.

Use `JoinKeyResolver` from `utils/join_key_resolver.py` when available.

---

## Pattern 3: Three-way (PostgreSQL → MongoDB → DuckDB)

**Scenario:** Combine relational ids, document attributes, and analytical columns.

**Steps:**

1. PostgreSQL worker: base keys / facts.
2. Mongo worker: enrich using transformed join keys.
3. Merge conductor: align on shared logical id.
4. DuckDB worker: aggregates/windows on the merged set (or push down if one engine holds all needed columns).

---

## Failure recovery

If a join returns empty:

1. Check INT vs STRING and prefix mismatches (`resolve_join_key`, `resolve_tcga_id` for TCGA barcodes).
2. Confirm collection/table names exist in the **connected** seed (e.g. no `reviews` in Mongo for default Yelp).
3. Retry after normalization.

---

## Injection test

Q: What are the steps for a classic PostgreSQL → MongoDB join with `CUST-` prefixes?

A: Query PostgreSQL for base ids, transform with `f"CUST-{id}"`, query Mongo with those strings, merge on the same logical customer.
