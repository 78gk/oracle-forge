# NULL Guard Patterns for LIKE Queries on Nullable Text Columns

## Rule

Always add `WHERE column IS NOT NULL` before any `LIKE` or `LOWER()` filter on nullable text columns.

In SQL, `NULL LIKE '%pattern%'` evaluates to `NULL` (not `FALSE`). Without a NULL guard, rows with `NULL` in the text column are silently excluded from counts, which can cause incorrect totals or errors depending on the database engine.

## Standard Pattern

```sql
SELECT COUNT(*) FROM table
WHERE column IS NOT NULL
  AND (
    LOWER(column) LIKE '%term1%'
    OR LOWER(column) LIKE '%term2%'
  );
```

## Example — GitHub READMEs (Probe U4)

```sql
SELECT COUNT(*) FROM repositories
WHERE readme_text IS NOT NULL
  AND (
    LOWER(readme_text) LIKE '%machine learning%'
    OR LOWER(readme_text) LIKE '%deep learning%'
  );
```

## Applies To

- SQLite: `readme_text`, `description`, `notes`
- PostgreSQL: `support_tickets.description`, `customers.notes`
- DuckDB: any TEXT column not declared NOT NULL

## Injection Test

Q: How should I filter a nullable text column with LIKE?
A: Always add WHERE column IS NOT NULL before the LIKE filter. NULL LIKE '%x%' is NULL not FALSE.
