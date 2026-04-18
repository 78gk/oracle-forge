# Domain layer changelog

## 2026-04-17 — Align KB with DataAgentBench seeds

- **`databases/postgresql_schemas.md`:** Document `bookreview_db`, `googlelocal_db`, `crm_support`, `pancancer_clinical`, `patent_CPCDefinition` as loaded from DAB SQL.
- **`databases/mongodb_schemas.md`:** Document `articles_db.articles` for AG News.
- **`databases/sqlite_schemas.md`:** Document `metadata.db` (`article_metadata`, `authors`); paths, quoting for `#` in identifiers; clarify distinct `review_query.db` per benchmark.
- **`databases/duckdb_schemas.md`:** Replace fictional PANCANCER `gene_expression` sketch with **`Mutation_Data`** / **`RNASeq_Expression`**; stock quoting note; clarify illustrative vs verified sections.
- **`domain_terms/authoritative_tables.md`:** Replace fictional `finance.fact_revenue` story with actual **`crm_support`** tables; state hypothetical finance cube separately.
- **`domain_terms/business_glossary.md`:** Ground crmarenapro terms in **`crm_support`** + introspection; mark NPS/revenue rubrics as conditional.
- **`joins/join_key_mappings.md`:** PANCANCER joins use **`ParticipantBarcode`** / **`clinical_info`**; deprecate old gene_expression wording.
- **`joins/cross_db_join_patterns.md`:** Remove erroneous file wrapper; add grounding note for real vs reference schemas.

## 2026-04-09 — v2 domain layer

### Added — databases

- `postgresql_schemas.md` — Yelp + reference telecom/healthcare sketches
- `mongodb_schemas.md` — Yelp + reference docs
- `sqlite_schemas.md` — Default bookreview path
- `duckdb_schemas.md` — Yelp + reference analytics sketches

### Added — joins

- `join_key_mappings.md`
- `cross_db_join_patterns.md`

### Added — unstructured / terms

- `unstructured/*`, `domain_terms/business_glossary.md`, etc.

Each KB file is intended for agent context injection; validate against live seeds after major data loads.
