# KB Injection Test Report

**Date:** 2026-04-12 15:25:57  
**Model:** llama-3.3-70b-versatile  
**KB Path:** kb  
**Pass Rate:** 21/21 (100.0%)

## Summary

| Total | Passed | Failed | Errors | Pass Rate |
|-------|--------|--------|--------|-----------|
| 21 | 21 | 0 | 0 | 100.0% |

## Results by Document

### ✅ architecture/memory.md — PASS (100%)

**Question:** What are the three layers of Claude Code's memory system?  
**LLM Answer:** The three layers of Claude Code's memory system are:  1. Layer 1 - MEMORY.md (index) 2. Layer 2 - Topic Files (on-demand) 3. Layer 3 - Session Transcripts (searchable)  
**Matched:** `MEMORY.md`, `topic files`, `session transcripts`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ architecture/autodream_consolidation.md — PASS (100%)

**Question:** When does autoDream run and what does it do?  
**LLM Answer:** autoDream runs on Fridays (weekly) or when the correction log exceeds 50 entries. It compresses session transcripts into persistent memory without losing signal, and its output is written to resolved_patterns.md.  
**Matched:** `Fridays`, `compresses`, `session transcripts`, `resolved_patterns`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ architecture/tool_scoping_philosophy.md — PASS (100%)

**Question:** Why are 40+ tight tools better than 5 generic tools?  
**LLM Answer:** Narrow tools enforce precise DB-specific capability boundaries. A generic "query_database" tool can't handle MongoDB aggregation pipelines vs SQL vs DuckDB analytical optimizations.  
**Matched:** `narrow`, `precise`, `DB-specific`, `boundaries`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ architecture/openai_layers.md — PASS (100%)

**Question:** What are the minimum three context layers for Oracle Forge?  
**LLM Answer:** The minimum three context layers for Oracle Forge are:  1. Schema (Layer A) 2. Institutional (Layer B) 3. Correction log (Layer C)  
**Matched:** `Schema`, `institutional`, `correction log`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ architecture/conductor_worker_pattern.md — PASS (100%)

**Question:** How does the agent handle multi-database queries?  
**LLM Answer:** The Conductor spawns database-specific workers (one per DB), then merges results from all workers into a unified response.  
**Matched:** `Conductor`, `spawns`, `workers`, `merges`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ architecture/evaluation_harness_schema.md — PASS (100%)

**Question:** What is pass@1 and how is it calculated?  
**LLM Answer:** pass@1 is calculated as the number of correct first answers divided by the total number of queries. The document also mentions that there should be a minimum of 50 trials per query.  
**Matched:** `correct first answers`, `queries`, `minimum`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/databases/postgresql_schemas.md — PASS (100%)

**Question:** What is the format of Yelp business_id?  
**LLM Answer:** The format of Yelp business_id is "abc123def456" (TEXT).  
**Matched:** `abc123def456`, `TEXT`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/databases/mongodb_schemas.md — PASS (100%)

**Question:** What is the format of customer_id in MongoDB telecom collection?  
**LLM Answer:** The format of customer_id in MongoDB telecom collection is "CUST-1234567" (STRING with prefix).  
**Matched:** `CUST-`, `STRING`, `prefix`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/databases/sqlite_schemas.md — PASS (100%)

**Question:** What format are customer_ids in SQLite?  
**LLM Answer:** INTEGER, no prefix.  
**Matched:** `INTEGER`, `no prefix`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/databases/duckdb_schemas.md — PASS (100%)

**Question:** What is DuckDB used for in DAB?  
**LLM Answer:** DuckDB is used for analytical queries that aggregate across large datasets.  
**Matched:** `analytical`, `aggregate`, `large datasets`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/joins/join_key_mappings.md — PASS (100%)

**Question:** How do I join PostgreSQL subscriber_id to MongoDB?  
**LLM Answer:** To join PostgreSQL subscriber_id to MongoDB, use the `resolve_join_key` function to apply the transformation `f"CUST-{subscriber_id}"`. This will convert the integer subscriber_id in PostgreSQL to a string in the format "CUST-{subscriber_id}" that matches the format in MongoDB.  
**Matched:** `resolve_join_key`, `CUST-`, `transformation`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/joins/cross_db_join_patterns.md — PASS (75%)

**Question:** What are the steps for PostgreSQL to MongoDB join?  
**LLM Answer:** The steps for PostgreSQL to MongoDB join are: 1. Query PostgreSQL first for customer_ids. 2. Transform each ID: f"CUST-{customer_id}" 3. Query MongoDB with transformed IDs 4. Merge results on transformed key  
**Matched:** `transform`, `query Mongo`, `merge`  
**Missing:** `Query PG`  
**Match Rate:** 75%  

---

### ✅ domain/unstructured/text_extraction_patterns.md — PASS (100%)

**Question:** How do I extract negative sentiment from support ticket text?  
**LLM Answer:** Use the `negative_indicators` list with `.lower()` and `any()`. This involves converting the text to lowercase and checking if any of the negative indicators are present in the text.  
**Matched:** `negative_indicators`, `.lower()`, `any()`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/unstructured/sentiment_mapping.md — PASS (100%)

**Question:** How does negation affect sentiment classification?  
**LLM Answer:** According to the document, negation affects sentiment classification in the following way: If "not" precedes an indicator, the sentiment is flipped. For example, "not good" is classified as negative, and "not bad" is classified as non-negative. Additionally, "not working" is already in the negative list and is classified as negative, and "couldn't be better" is classified as positive due to the double negative.  
**Matched:** `not good`, `negative`, `not bad`, `non-negative`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ domain/domain_terms/business_glossary.md — PASS (100%)

**Question:** What does 'active customer' mean in telecom?  
**LLM Answer:** Purchased in last 90 days AND churn_date IS NULL.  
**Matched:** `last 90 days`, `churn_date IS NULL`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ correction/failure_log.md — PASS (100%)

**Question:** What went wrong on Q023 and what's the fix?  
**LLM Answer:** On Q023, the agent attempted to join PostgreSQL subscriber_id (INT) directly with MongoDB collection (String format "CUST-{id}"), which resulted in an INT to String join failure.  The correct approach is to use resolve_join_key(subscriber_id, 'postgres', 'mongodb') → returns 'CUST-{id}'.  
**Matched:** `INT to String`, `resolve_join_key`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ correction/failure_by_category.md — PASS (100%)

**Question:** What are DAB's four failure categories?  
**LLM Answer:** DAB's four failure categories are:  1. Multi-Database Routing Failure (Category 1) 2. Ill-Formatted Join Key Mismatch (Category 2) 3. Unstructured Text Extraction Failure (Category 3) 4. Domain Knowledge Gap (Category 4)  
**Matched:** `Multi-Database`, `Join Key`, `Unstructured`, `Domain Knowledge`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ correction/resolved_patterns.md — PASS (100%)

**Question:** What is the confidence score for PG-INT to Mongo-String transformation?  
**LLM Answer:** The confidence score for the PG-INT to Mongo-String transformation is 14/14 successes.  
**Matched:** `14/14`, `successes`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ correction/regression_prevention.md — PASS (100%)

**Question:** What happens if regression test fails?  
**LLM Answer:** If regression test fails, the following steps are taken:  1. Revert the change immediately 2. Log failure to failure_log.md 3. Do not deploy until all regression tests pass 4. Update the file with new failure mode.  
**Matched:** `Revert`, `log failure`, `do not deploy`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ evaluation/dab_scoring_method.md — PASS (100%)

**Question:** What is pass@1?  
**LLM Answer:** pass@1 = (number of correct first answers) / (total queries)  
**Matched:** `correct first answers`, `total queries`  
**Missing:** —  
**Match Rate:** 100%  

---

### ✅ evaluation/submission_format.md — PASS (100%)

**Question:** What files are required for DAB submission?  
**LLM Answer:** The files required for DAB submission are:  1. `submission/team_name_results.json` (the results JSON file)  2. `AGENT.md` (architecture description)  
**Matched:** `results JSON`, `AGENT.md`  
**Missing:** —  
**Match Rate:** 100%  

---
