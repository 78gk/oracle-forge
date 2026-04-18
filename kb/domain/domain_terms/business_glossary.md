# Domain Term Definitions by Dataset

## Telecom Industry

| Term | Naive Interpretation | Correct Definition (for DAB) |
| ---- | -------------------- | ----------------------------- |
| "active customer" | Has row in subscribers table | Purchased in last 90 days AND churn_date IS NULL |
| "churn" | Cancelled service | churn_date IS NOT NULL |
| "high-value customer" | High monthly_revenue | monthly_revenue > 100 AND plan_type = 'postpaid' |
| "fiscal quarter" | Calendar Q3 (Jul-Sep) | Telecom fiscal: Q3 = Oct-Dec |

## Retail (Yelp)

| Term | Naive Interpretation | Correct Definition |
| ---- | -------------------- | ------------------ |
| "popular business" | High `business.review_count` alone | `business.review_count > 100` **and** average per-review rating from **`review`** (PostgreSQL `review.stars` / DuckDB `review.rating`) above the threshold — **`business` has no `stars` column** in the seeded Postgres schema |
| "recent review" | Last 30 days | Filter **`review.date`** (PostgreSQL/DuckDB) to the window; do not assume a Mongo `reviews` collection |
| "power user" | High `user.review_count` | **`user.review_count` > 50** plus high **`useful`/`funny`/`cool`** on **`user`** (there is **no `fans`** column in the default Yelp Postgres `user` table) |
| "open business with high rating" | `stars >= 4.5` on `business` | **`business.is_open = 1`** **and** aggregate average from **`review`** ≥ threshold (same stars/rating sources as above) |

## Healthcare

| Term | Naive Interpretation | Correct Definition |
| ---- | -------------------- | ------------------ |
| "readmission" | Same patient, same hospital | patient_id matches AND days_between < 30 |
| "out-of-network" | Provider not in network | provider_npi NOT IN network_list |
| "denied claim" | claim_status = 'denied' | status IN ('denied', 'rejected') |

## crmarenapro Dataset

**Ground truth:** DataAgentBench loads **PostgreSQL `crm_support`** (support cases, email, chat — see `authoritative_tables.md` and `postgresql_schemas.md`). It does **not** expose generic `customers`, `orders`, `last_purchase_date`, or NPS score columns unless they appear in the **file-backed** SQLite/DuckDB for this benchmark. **Introspect** the active connection before applying any row below.

| Term | Naive Interpretation | Correct approach (for DAB) |
| ---- | -------------------- | -------------------------- |
| "open case" / "ticket" | Any row in a generic `tickets` table | Use **`"Case"`** in `crm_support`: interpret **`status`** / **`closeddate`** (e.g. open ⇔ `closeddate` null or status not terminal — **verify enum values in data**). |
| "active customer" (if purchase semantics apply) | Row in `customers` | Only valid if **`customers` / `last_purchase_date`** exist in the **SQLite/DuckDB** you have open — **not** in `crm_support` Postgres as seeded. |
| "revenue" | SUM of all order amounts | **`crm_support` Postgres has no standard revenue fact table.** If the question is revenue, query the **crmarenapro file DBs** (`products_orders`, `sales_pipeline`, etc.) or answer from available columns after introspection. Do **not** invent `finance.fact_revenue`. |
| "NPS promoter" | Score > 8 on 0–10 | NPS-style scores appear only if a column exists in the **actual** table you query. The **–100 to +100** / threshold **≥ 50** story is a **hypothetical** rubric — **do not apply** unless the schema contains that metric. |

### Illustrative retail-cube semantics (file DBs or synthetic evals only)

When **`orders`**, **`last_purchase_date`**, or NPS columns **actually exist** in the connected SQLite/DuckDB:

- **Active customer (purchase-based):** at least one purchase in the last 90 days — e.g. `last_purchase_date >= CURRENT_DATE - INTERVAL '90 days'` when that column exists.
- **Revenue:** `SUM(amount) WHERE status NOT IN ('refunded', 'cancelled', 'returned')` when those columns exist.
- **NPS (hypothetical –100…+100 scale):** promoter if score ≥ 50 — only if the column matches that scale.

---

## Where to Find Definitions

Domain terms are not always materialized as columns. **Always** reconcile with `information_schema` / `PRAGMA table_info` / sample documents for the **active** database and path.

Load this file before generating SQL for ambiguous terms.

---

## Injection tests

Q: What does "active customer" mean in telecom?

A: Purchased in last 90 days AND churn_date IS NULL (telecom reference schema — not `crm_support`).

Q: Where are "open cases" for DataAgentBench crmarenapro Postgres?

A: Table **`"Case"`** in database **`crm_support`** — use **`status`**, **`closeddate`**, and **`createddate`** per actual values in the table.

Q: Can I use `finance.fact_revenue` for crmarenapro?

A: **No** in the seeded **`crm_support`** database — that object does not exist. See `authoritative_tables.md`.
