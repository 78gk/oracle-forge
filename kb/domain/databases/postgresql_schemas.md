# PostgreSQL Schemas for DAB Datasets

This document covers: (1) **`oracleforge`** — Yelp mirror from `scripts/seed_yelp_postgres.py` (default Oracle Forge); (2) **additional DataAgentBench databases** created when you load `query_*/query_dataset/*.sql` (e.g. via `scripts/reset_and_seed_dab_docker.py`) — `bookreview_db`, `googlelocal_db`, `crm_support`, `pancancer_clinical`, `patent_CPCDefinition`.

The **telecom/healthcare reference** section at the end is conceptual only — those tables are **not** created by default Docker unless you add separate seeds.

There are no `subscribers`, `patients`, or `claims` tables in the default Yelp-only deployment.

## Yelp Dataset (primary for validation)

### Table: business

- business_id (TEXT, PK)
- name (TEXT)
- description (TEXT)
- review_count (INTEGER)
- is_open (INTEGER) — 0 = closed, 1 = open
- attributes (TEXT) — Yelp API-style keys embedded as text (e.g. `'BikeParking': 'True'`, `BusinessParking: {… 'garage': True …}`), not natural-language phrases like “bike parking”. Match keys/structure when filtering amenities; see `scripts/reconcile_yelp_ground_truth.py` for benchmark-aligned parking predicates.
- hours (TEXT)
- state_code (TEXT) — derived/normalized state (not a generic `city`/`state` pair from the KB’s older sketch)
- accepts_credit_cards (BOOLEAN)
- has_wifi (BOOLEAN)
- primary_categories (TEXT) — pipe-joined category tags

There is **no** `stars` column on `business` in this deployment; star ratings live in **`review.stars`** (and in Mongo/DuckDB as described in those KB files).

### Table: business_category

- business_id (TEXT, PK part) — FK → `business.business_id`
- category (TEXT, PK part)

### Table: review

- review_id (TEXT, PK)
- user_id (TEXT) — matches `"user".user_id`
- business_id (TEXT) — matches `business.business_id` (join to DuckDB via `business_id` ↔ `business_ref` naming in DuckDB)
- stars (INTEGER) — 1–5 (same semantics as DuckDB `review.rating`)
- date (TEXT)
- text (TEXT)

### Table: user

- user_id (TEXT, PK)
- name (TEXT)
- review_count (INTEGER)
- yelping_since (TEXT)
- useful (INTEGER)
- funny (INTEGER)
- cool (INTEGER)
- elite (TEXT)

There is **no** `average_stars` column; user-level aggregates differ from the older KB sketch.

---

## DataAgentBench: `bookreview_db` (from `query_bookreview/query_dataset/books_info.sql`)

Single table **`books_info`**:

- title, subtitle, author (TEXT)
- rating_number (BIGINT)
- features, description, categories, details (TEXT — often JSON-ish strings in dumps)
- price (DOUBLE PRECISION)
- store (TEXT)
- book_id (TEXT)

---

## DataAgentBench: `googlelocal_db` (from `query_googlelocal/query_dataset/business_description.sql`)

Single table **`business_description`**:

- name, gmap_id, description, hours, state (TEXT)
- num_of_reviews (BIGINT)
- **MISC** (TEXT) — quoted identifier in SQL; Google Maps–style attributes JSON

---

## DataAgentBench: `crm_support` (from `query_crmarenapro/query_dataset/support.sql`)

Salesforce-style support objects. There are **no** schemas named `finance` or `sales`, and **no** `fact_revenue` / `order_line` tables in this seed.

### Table: `Case` (quoted identifier — use `"Case"` in SQL)

- id, priority, subject, description, status (TEXT)
- contactid, accountid, ownerid (TEXT)
- createddate, closeddate (TEXT)
- orderitemid__c, issueid__c (TEXT)

### Table: `casehistory__c`

- id, caseid__c, oldvalue__c, newvalue__c, createddate, field__c (TEXT)

### Table: `emailmessage`

- id, subject, textbody, parentid, fromaddress, toids, messagedate, relatedtoid (TEXT)

### Table: `issue__c`

- id, name, description__c (TEXT)

### Table: `knowledge__kav`

- id, title, faq_answer__c, summary, urlname (TEXT)

### Table: `livechattranscript`

- id, caseid, accountid, ownerid, body, endtime, livechatvisitorid, contactid (TEXT)

Pair with file-backed SQLite/DuckDB under `query_crmarenapro/query_dataset/` (see `sqlite_schemas.md`, `duckdb_schemas.md`).

---

## DataAgentBench: `pancancer_clinical` (from `query_PANCANCER_ATLAS/query_dataset/pancancer_clinical.sql`)

Single wide table **`clinical_info`** (~99 columns): TCGA clinical and pathologic attributes.

- **patient_id** (TEXT) — join to DuckDB `ParticipantBarcode` / sample barcodes after TCGA normalization (see `join_key_mappings.md`).
- Examples of other columns: `Patient_description`, `days_to_birth`, `days_to_death`, `histological_type`, `tumor_tissue_site`, `pathologic_stage`, `clinical_stage`, `race`, `ethnicity`, `diagnosis`, …

Introspect `information_schema.columns` if a specific attribute is required; do not invent column names.

---

## DataAgentBench: `patent_CPCDefinition` (from `query_PATENTS/query_dataset/patent_CPCDefinition.sql`)

Single table **`cpc_definition`** (CPC hierarchy / titles):

- symbol, titleFull, titlePart, level, status, dateRevised (TEXT where noted in dump)
- JSON/array-oriented fields stored as text in dump: applicationReferences, childGroups, children, definition, glossary, informativeReferences, ipcConcordant, limitingReferences, parents, precedenceLimitingReferences, residualReferences, rules, scopeLimitingReferences, synonyms, breakdownCode, notAllocatable

---

## Reference: Telecom / Healthcare (not in default Postgres seed)

The following are **conceptual** layouts used in join-key documentation and some eval scenarios. They are **not** created by the default Oracle Forge Postgres container.

### Table: subscribers (reference)

- subscriber_id (INT, PK)
- plan_type (TEXT)
- activation_date (DATE)
- churn_date (DATE)
- monthly_revenue (DECIMAL)

### Table: support_tickets (reference)

- ticket_id (TEXT, PK)
- subscriber_id (INT)
- issue_type (TEXT)
- resolution_time_hours (INT)

### Table: patients (reference)

- patient_id (INT, PK)
- date_of_birth (DATE)
- insurance_plan_id (TEXT)
- state (TEXT)

### Table: claims (reference)

- claim_id (TEXT, PK)
- patient_id (INT)
- provider_npi (INT)
- service_date (DATE)
- amount (DECIMAL)
- status (TEXT)

**Healthcare join note:** patient_id is INT in PostgreSQL, `"PT-{INT}"` in MongoDB; provider_npi is INT in PostgreSQL, `"NPI-{INT}"` in MongoDB. Use `resolve_join_key` where applicable.

## Critical join note (telecom reference)

Customer IDs in PostgreSQL are INT. Same logical customers in MongoDB are `"CUST-{INT}"` strings. **Use `resolve_join_key` with** `f"CUST-{customer_id}"` when joining reference telecom collections.

## Injection tests

Q: What columns does `business` have in the seeded Yelp Postgres schema?

A: `business_id`, `name`, `description`, `review_count`, `is_open`, `attributes`, `hours`, `state_code`, `accepts_credit_cards`, `has_wifi`, `primary_categories` (no `stars` on `business`).

Q: Does DataAgentBench `crm_support` include `finance.fact_revenue`?

A: **No.** It has Salesforce-style tables such as `"Case"`, `emailmessage`, `casehistory__c`, etc. See the `crm_support` section above.

Q: What Postgres table holds TCGA clinical facts for PANCANCER_ATLAS?

A: Database `pancancer_clinical`, table **`clinical_info`**, with **`patient_id`** among many clinical columns.
