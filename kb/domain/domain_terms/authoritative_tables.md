# Authoritative vs Deprecated Tables

## crmarenapro Revenue Tables

**Authoritative:** `finance.fact_revenue`
- Audited, updated nightly
- Deduplicated; bundle products counted once
- Use for ALL revenue totals, FY summaries, and financial reporting

**DEPRECATED:** `sales.order_line`
- Double-counts bundled products — never use for revenue totals
- Still queryable but produces ~20% inflated figures due to bundle line expansion
- Retained for legacy compatibility only

Rule: whenever a query requests "total sales", "revenue", or "FY totals" on crmarenapro, always use `finance.fact_revenue`.

```sql
-- Correct
SELECT SUM(revenue_amount) FROM finance.fact_revenue
WHERE order_date BETWEEN '2024-07-01' AND '2025-06-30';

-- Wrong (deprecated, double-counts bundles)
SELECT SUM(amount) FROM sales.order_line ...;
```

## Injection Test

Q: Which table should I use for total sales on crmarenapro?
A: finance.fact_revenue (authoritative, audited nightly). Never use sales.order_line — it double-counts bundled products.
