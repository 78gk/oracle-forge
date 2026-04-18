# Authoritative vs Deprecated / Misleading Table Names

## DataAgentBench `crm_support` (PostgreSQL) — what is actually loaded

When you seed from **`DataAgentBench/query_crmarenapro/query_dataset/support.sql`** (e.g. `scripts/reset_and_seed_dab_docker.py`), database **`crm_support`** contains **Salesforce-style** support objects only.

**Authoritative for this deployment (support / cases / email / chat):**

- **`"Case"`** — service cases (use quoted identifier in SQL). Key fields: `id`, `status`, `priority`, `subject`, `description`, `contactid`, `accountid`, `ownerid`, `createddate`, `closeddate`, `issueid__c`, `orderitemid__c`.
- **`casehistory__c`** — field history on cases (`caseid__c`, `field__c`, `oldvalue__c`, `newvalue__c`, `createddate`).
- **`emailmessage`** — emails linked to cases (`parentid`, `textbody`, `fromaddress`, `messagedate`, …).
- **`issue__c`** — issue catalog (`name`, `description__c`).
- **`knowledge__kav`** — knowledge articles (`title`, `faq_answer__c`, `summary`, `urlname`).
- **`livechattranscript`** — live chat bodies tied to `caseid`.

**There is no `finance` schema, no `sales` schema, no `finance.fact_revenue`, and no `sales.order_line` in this seed.** Do not generate SQL that references those objects against **`crm_support`**.

For revenue-like questions **on this benchmark**, either:

1. Use whatever revenue fields exist in the **file-backed** SQLite/DuckDB under `query_crmarenapro/query_dataset/` (introspect `core_crm.db`, `products_orders.db`, `sales_pipeline.duckdb`, `activities.duckdb`, `territory.db`), or  
2. State that revenue is not modeled in **`crm_support`** Postgres and query the appropriate file DB.

---

## Hypothetical finance cube (not in `crm_support` seed)

Some training examples use a **fictional** star schema:

- **`finance.fact_revenue`** — illustrative “audited revenue” fact.
- **`sales.order_line`** — illustrative line-level table that can double-count bundles.

Those names are **not** created by the DataAgentBench `support.sql` load. If a prompt assumes them, either switch to a database where they exist or **reject the assumption** and use **`crm_support`** + file DBs as documented in `kb/domain/databases/postgresql_schemas.md` and `duckdb_schemas.md`.

---

## Injection tests

Q: Which table should I use for “total sales” in Postgres `crm_support`?

A: **None by that name.** `crm_support` has no `finance.fact_revenue`. Use **`"Case"`** / related support tables for case analytics, or introspect the crmarenapro SQLite/DuckDB files for order/revenue fields.

Q: Does `sales.order_line` exist in DataAgentBench `crm_support`?

A: **No.**
